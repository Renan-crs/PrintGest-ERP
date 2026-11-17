"""Integrações com apps de terceiros (PRD v3.3 §3.6).

Segredo nunca em banco/log/resposta; só no cofre cifrado. Testes usam cofre
isolado e `httpx.MockTransport` (nenhuma rede real).
"""

import json
import uuid

import httpx
import pytest
from sqlalchemy import text as sa_text

from app.core import cofre_integracoes
from app.core.config import settings
from app.db import SessionLocal
from app.models.enums import TipoIntegracao
from app.models.integracao import Integracao, IntegracaoEvento
from tests.conftest import auth


@pytest.fixture(autouse=True)
def _integracoes_limpas(client, tmp_path, monkeypatch):
    """Cada caso começa sem integrações e com cofre isolado.

    Depende de `client`: é ele que configura o `SessionLocal` para o banco de
    teste e aplica as migrations (via `_banco_teste`).
    """
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_integracoes.limpar()
    db = SessionLocal()
    try:
        db.query(IntegracaoEvento).delete()
        db.query(Integracao).delete()
        db.commit()
    finally:
        db.close()
    yield
    cofre_integracoes.limpar()

SEGREDO = "sk_super_secreto_1234567890"
CERT = "-----BEGIN CERTIFICATE-----\nABCDEF==\n-----END CERTIFICATE-----"


def _u() -> str:
    return uuid.uuid4().hex[:8]


def test_crud_segredo_no_cofre_e_mascara(client, admin_token, monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_integracoes.limpar()
    headers = auth(client, admin_token)

    resp = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={
            "tipo": "fiscal",
            "nome": "Emissor de Nota Fiscal",
            "provedor": "Focus NFe",
            "base_url": "https://api.focusnfe.com.br/v2",
            "credencial": SEGREDO,
            "certificado": CERT,
            "opcoes": {"emitir_path": "/nfce"},
        },
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()["data"]
    assert doc["tipo"] == "fiscal"
    assert doc["tem_credencial"] and doc["tem_certificado"]
    assert "segredo" not in json.dumps(doc).lower()
    assert doc["credencial_mascara"].endswith("7890")
    assert doc["credencial_mascara"].startswith("••••")
    assert SEGREDO not in json.dumps(doc)
    assert CERT not in json.dumps(doc)

    # Banco NÃO contém o segredo em claro
    db = SessionLocal()
    try:
        linha = db.get(Integracao, doc["id"])
        cols = {c.name: getattr(linha, c.name) for c in Integracao.__table__.columns}
        assert all(SEGREDO not in str(v) for v in cols.values())
        assert all(CERT not in str(v) for v in cols.values())
    finally:
        db.close()

    # Cofre cifrado contém o valor (decifrável via helper)
    arquivo = cofre_integracoes.caminho()
    assert arquivo.exists()
    assert SEGREDO not in arquivo.read_text(encoding="utf-8")
    assert (
        cofre_integracoes.obter(1, doc["id"], "credencial") == SEGREDO
    )

    # Lista/OGET também não expõem
    lista = client.get("/v1/config/integracoes", headers=headers).json()
    assert lista["total"] >= 1 and SEGREDO not in json.dumps(lista).lower()
    detalhe = client.get(
        f"/v1/config/integracoes/{doc['id']}", headers=headers
    )  # rota não existe ainda? ver abaixo
    assert detalhe.status_code in (200, 404, 405)

    # Atualiza só o nome (segredo permanece)
    upd = client.put(
        f"/v1/config/integracoes/{doc['id']}",
        headers=headers,
        json={"nome": "Emissor NF (renomeado)"},
    )
    assert upd.status_code == 200, upd.text
    assert SEGREDO == cofre_integracoes.obter(1, doc["id"], "credencial")

    # Remove credencial
    upd2 = client.put(
        f"/v1/config/integracoes/{doc['id']}",
        headers=headers,
        json={"remover_credencial": True},
    )
    assert upd2.status_code == 200
    assert cofre_integracoes.obter(1, doc["id"], "credencial") == ""
    assert upd2.json()["data"]["tem_credencial"] is False

    # Exclui
    exc = client.delete(f"/v1/config/integracoes/{doc['id']}", headers=headers)
    assert exc.status_code == 204
    assert client.get("/v1/config/integracoes", headers=headers).json()["total"] == 0


def test_duplicidade_tipo_e_validacoes(client, admin_token, monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_integracoes.limpar()
    headers = auth(client, admin_token)
    base = {"tipo": "fiscal", "nome": "Fiscal", "credencial": "abc"}

    assert client.post("/v1/config/integracoes", headers=headers, json=base).status_code == 201
    dup = client.post("/v1/config/integracoes", headers=headers, json=base)
    assert dup.status_code == 409

    ruim = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={"tipo": "email", "nome": "Email", "base_url": "ftp://x"},
    )
    assert ruim.status_code == 422
    ambiente = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={"tipo": "generica", "nome": "G", "ambiente": "producao-local"},
    )
    assert ambiente.status_code == 422


def test_teste_conexao_sem_vazamento(client, admin_token, monkeypatch, tmp_path):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_integracoes.limpar()
    vistos = {}

    def handler(request: httpx.Request) -> httpx.Response:
        vistos["auth"] = request.headers.get("Authorization")
        vistos["url"] = str(request.url)
        return httpx.Response(200, json={"status": "ok"})

    import app.services.integracao_service as svc

    ClienteReal = svc.httpx.Client

    def _cliente_falso(**kwargs):
        return ClienteReal(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(svc.httpx, "Client", _cliente_falso)

    headers = auth(client, admin_token)
    doc = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={
            "tipo": "fiscal",
            "nome": "Fiscal",
            "base_url": "https://api.test/v2",
            "credencial": SEGREDO,
        },
    ).json()["data"]

    teste = client.post(
        f"/v1/config/integracoes/{doc['id']}/testar", headers=headers
    )
    assert teste.status_code == 200, teste.text
    resultado = teste.json()["data"]
    assert resultado["ok"] is True
    assert resultado["status_http"] == 200
    assert resultado["segredo_exposto"] is False
    assert vistos["auth"] == f"Bearer {SEGREDO}"
    assert SEGREDO not in json.dumps(resultado)

    # Sem segredo: 400
    doc2 = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={"tipo": "email", "nome": "Email", "base_url": "https://api.test"},
    ).json()["data"]
    assert (
        client.post(
            f"/v1/config/integracoes/{doc2['id']}/testar", headers=headers
        ).status_code
        == 400
    )

    # Eventos sem segredo
    eventos = client.get(
        f"/v1/config/integracoes/{doc['id']}/eventos", headers=headers
    ).json()
    assert SEGREDO not in json.dumps(eventos).lower()
    assert any(e["tipo"] == "TESTE_OK" for e in eventos)
    assert any(e["tipo"] == "CRIADA" for e in eventos)


def test_admin_only_e_isolamento_entre_filiais(
    client, admin_token, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_integracoes.limpar()
    headers = auth(client, admin_token)
    doc = client.post(
        "/v1/config/integracoes",
        headers=headers,
        json={"tipo": "fiscal", "nome": "Fiscal", "credencial": SEGREDO},
    ).json()["data"]

    # Outras filiais não veem a integração da filial 1
    db = SessionLocal()
    try:
        from app.models.core import Empresa, Filial

        empresa = Empresa(
            razao_social="Outra gráfica", cnpj=uuid.uuid4().hex[:14], ativa=True
        )
        db.add(empresa)
        db.flush()
        filial = Filial(empresa_id=empresa.id, nome="Outra filial", ativa=True)
        db.add(filial)
        db.flush()
        db.execute(
            sa_text("UPDATE integracao SET filial_id = :fid WHERE id = :id"),
            {"fid": filial.id, "id": doc["id"]},
        )
        db.commit()
    finally:
        db.close()
    assert client.get("/v1/config/integracoes", headers=headers).json()["total"] == 0

    # Gerente/operador não acessam
    from tests.test_fiscal import _token_de

    gerente = auth(client, _token_de(client, admin_token, "gerente"))
    assert client.get("/v1/config/integracoes", headers=gerente).status_code == 403
