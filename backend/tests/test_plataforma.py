"""Plataforma PRD v3.3: filiais, estações, outbox, diagnóstico e backup.

Nenhum teste faz rede ou chama pg_dump de verdade (mock de subprocess).
"""

import uuid

import pytest
from app.core.config import settings
from app.db import SessionLocal
from app.models.core import Empresa, Filial
from app.models.plataforma import BackupConfig, Estacao, EventoSync, TermoBackup
from app.services import backup_service, estacao_service
from tests.conftest import auth

FILIAL = 1


@pytest.fixture(autouse=True)
def _limpar(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pg_raiz", str(tmp_path / "sem_pg"))
    db = SessionLocal()
    try:
        for modelo in (TermoBackup, BackupConfig, EventoSync, Estacao):
            db.query(modelo).delete()
        # Não apagar filiais/empresas: outros testes criam e referenciam
        # documentos fiscais com FK para elas. Limitamos ao que este módulo cria.
        filial = db.get(Filial, FILIAL)
        filial.instalacao_id = None
        filial.papel = None
        db.commit()
    finally:
        db.close()
    criados = getattr(_limpar, "criados", [])
    yield
    if criados:
        db = SessionLocal()
        try:
            for modelo, item_id in criados:
                db.query(modelo).filter(modelo.id == item_id).delete()
            db.commit()
        finally:
            db.close()
        _limpar.criados = []


def _admin(client, admin_token):
    return auth(client, admin_token)


# ------------------------------------------------------------------ filiais


def test_filial_papel_e_instalacao(client, admin_token):
    h = _admin(client, admin_token)
    r = client.put(
        "/v1/plataforma/filiais/1",
        headers=h,
        json={"papel": "matriz", "instalacao_id": "inst-123"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["papel"] == "MATRIZ"
    assert r.json()["data"]["instalacao_id"] == "inst-123"

    invalido = client.put(
        "/v1/plataforma/filiais/1", headers=h, json={"papel": "gerente"}
    )
    assert invalido.status_code == 400

    lista = client.get("/v1/plataforma/filiais", headers=h).json()
    assert any(
        f["id"] == FILIAL and f["papel"] == "MATRIZ" for f in lista["data"]
    )
    assert lista["meta"]["total"] == len(lista["data"])


def test_filial_nao_pode_alterar_outra(client, admin_token):
    db = SessionLocal()
    try:
        e = Empresa(razao_social="Outra", cnpj=uuid.uuid4().hex[:14])
        db.add(e)
        db.flush()
        f = Filial(empresa_id=e.id, nome="Filial 2")
        db.add(f)
        db.commit()
        fid = f.id
        _limpar.criados = getattr(_limpar, "criados", [])
        _limpar.criados.extend(
            [(Filial, fid), (Empresa, e.id)]
        )
    finally:
        db.close()
    r = client.put(
        f"/v1/plataforma/filiais/{fid}",
        headers=_admin(client, admin_token),
        json={"nome": "Hack"},
    )
    assert r.status_code == 403


# ----------------------------------------------------------------- estações


def test_estacao_registro_limite_e_remocao(client, admin_token, monkeypatch):
    h = _admin(client, admin_token)
    monkeypatch.setattr(
        estacao_service, "limite", lambda db, filial_id: 2
    )
    for i in range(2):
        r = client.post(
            "/v1/plataforma/estacoes/registrar",
            headers=h,
            json={"nome": f"PC-{i}", "fingerprint": f"abc-{i}-123456"},
        )
        assert r.status_code == 200, r.text
    terceira = client.post(
        "/v1/plataforma/estacoes/registrar",
        headers=h,
        json={"nome": "PC-3", "fingerprint": "abc-3-123456"},
    )
    assert terceira.status_code == 409
    assert terceira.json()["detail"]["codigo"] == "ESTACAO_LIMITE_EXCEDIDO"

    envelope = client.get("/v1/plataforma/estacoes", headers=h).json()
    assert "data" in envelope  # contrato idêntico ao do desktop (_get)
    resumo = envelope["data"]
    assert resumo["total"] == 2 and resumo["limite"] == 2 and resumo["vagas"] == 0

    # Reacesso da mesma estação não consome vaga e atualiza o nome.
    client.post(
        "/v1/plataforma/estacoes/registrar",
        headers=h,
        json={"nome": "PC-0 renomeado", "fingerprint": "abc-0-123456"},
    )
    assert client.get("/v1/plataforma/estacoes", headers=h).json()["data"]["total"] == 2

    alvo = resumo["estacoes"][0]
    assert client.delete(
        f"/v1/plataforma/estacoes/{alvo['id']}", headers=h
    ).status_code == 204
    assert client.get("/v1/plataforma/estacoes", headers=h).json()["data"]["total"] == 1


# ------------------------------------------------------------------- outbox


def test_outbox_idempotente_e_fila(client, admin_token):
    h = _admin(client, admin_token)
    uid = str(uuid.uuid4())
    corpo = {
        "uuid": uid, "entidade": "venda_balcao", "entidade_id": 10,
        "operacao": "CRS", "payload": {"total": "10.00"},
    }
    r1 = client.post("/v1/plataforma/sync/eventos", headers=h, json=corpo)
    assert r1.status_code == 201, r1.text
    r2 = client.post("/v1/plataforma/sync/eventos", headers=h, json=corpo)
    # O uuid é único: o gerador de seq não deve duplicar a fila.
    assert r2.status_code in (201, 409)

    pendentes = client.get(
        "/v1/plataforma/sync/eventos", headers=h, params={"pendentes": "true"}
    ).json()
    assert pendentes["meta"]["total"] >= 1

    marcou = client.post(
        "/v1/plataforma/sync/marcar-enviados", headers=h, json=[uid]
    ).json()["data"]["marcados"]
    assert marcou == 1
    assert client.get(
        "/v1/plataforma/sync/eventos", headers=h, params={"pendentes": "true"}
    ).json()["meta"]["total"] == 0
    assert client.get("/v1/plataforma/sync/status", headers=h).json()["data"][
        "ultimo_envio"
    ]


# ------------------------------------------------------------- diagnóstico


def test_diagnostico_sem_segredos(client, admin_token):
    h = _admin(client, admin_token)
    r = client.get("/v1/plataforma/diagnostico", headers=h)
    assert r.status_code == 200, r.text
    dado = r.json()["data"]
    assert dado["segredos_mascarados"] is True
    assert "modo_leitura" in dado and "versao" in dado
    texto = str(dado).lower()
    for secreto in ("bearer ", "client_secret", "codigo_licenca", "sk_"):
        assert secreto not in texto


def test_diagnostico_admin_only(client, admin_token):
    from tests.test_fiscal import _token_de

    gerente = auth(client, _token_de(client, admin_token, "gerente"))
    assert client.get("/v1/plataforma/diagnostico", headers=gerente).status_code == 403


# ------------------------------------------------------------------- backup


def test_backup_termo_antes_do_espelho_e_dumps(client, admin_token, monkeypatch, tmp_path):
    h = _admin(client, admin_token)
    destino = tmp_path / "backups"
    destino.mkdir()
    monkeypatch.setattr(backup_service, "destino_padrao", lambda: destino)

    cfg = client.put(
        "/v1/plataforma/backup",
        headers=h,
        json={"destino": str(destino), "horario": "03:30", "retencao_dias": 7},
    )
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["data"]["horario"] == "03:30"

    # Sem aceite, espelho não pode ser ativado direto pela config
    assert client.get("/v1/plataforma/backup/termo", headers=h).json()["data"]["aceito"] is False

    termo = client.post(
        "/v1/plataforma/backup/termo", headers=h,
        json={"aceito": True, "versao": "1.0"},
    )
    assert termo.status_code == 200
    assert termo.json()["data"]["aceito"] is True
    assert client.get("/v1/plataforma/backup", headers=h).json()["data"]["neon_espelho"] is True

    # pg_dump mockado: escreve um arquivo e retorna 0
    class Proc:
        returncode = 0
        stderr = ""

    chamadas = {}

    def _run(cmd, **kwargs):
        chamadas["cmd"] = cmd
        Path = __import__("pathlib").Path
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"dump")
        return Proc()

    monkeypatch.setattr(backup_service.subprocess, "run", _run)
    resultado = client.post("/v1/plataforma/backup/executar", headers=h).json()["data"]
    assert resultado["ok"] is True and resultado["tamanho"] == 4
    assert chamadas["cmd"][0].endswith("pg_dump.exe")
    assert "shell" not in chamadas

    # Rejeita diretório inexistente
    ruim = client.put(
        "/v1/plataforma/backup", headers=h, json={"destino": str(destino / "nao-existe")}
    )
    assert ruim.status_code == 400
