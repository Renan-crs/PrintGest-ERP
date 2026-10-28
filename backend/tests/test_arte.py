"""Arte, prova e aprovação (M3, PRD v3.0 §3.5).

Cobre: upload de versões (v1, v2…), decisão do cliente (aprovada / ajuste
com comentários), estado derivado da arte, link público com token/expiração,
validações (extensão bloqueada, arquivo vazio, ajuste sem comentários) e a
incorporação no status da OS ("Aguardando arte"/"Aguardando aprovação" +
gate: produção não inicia sem arte aprovada).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import arte_aprovada, auth

client = TestClient(app)


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_os(client_fixture, token):
    resp = client_fixture.post(
        "/v1/os",
        headers=auth(client_fixture, token),
        json={
            "tipo": "os",
            "cliente_id": _criar_cliente(client_fixture, token)["id"],
            "itens": [{"descricao_avulsa": "Cartão visita", "quantidade": 100, "valor_unitario": 0.5}],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_cliente(client_fixture, token):
    resp = client_fixture.post(
        "/v1/clientes",
        headers=auth(client_fixture, token),
        json={"nome_razao": f"Cliente Arte {_u()}", "tipo_pessoa": "pf"},
    )
    return resp.json()["data"]


def _upload(client_fixture, token, os_id, filename="arte.png", conteudo=None):
    if conteudo is None:
        conteudo = io.BytesIO(b"PNG fake para teste " + os.urandom(16))
    return client_fixture.post(
        f"/v1/os/{os_id}/arte",
        headers=auth(client_fixture, token),
        files={"arquivo": (filename, conteudo, "image/png")},
    )


# ------------------------------------------------------------------ upload


def test_primeira_upload_e_v1(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = _upload(client, admin_token, os_criada["id"])
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["versao"] == 1
    assert data["nome_arquivo"] == "arte.png"
    assert len(data["hash_sha256"]) == 64
    assert data["tamanho_bytes"] > 0


def test_segunda_upload_incrementa_versao(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    _upload(client, admin_token, os_criada["id"])
    resp = _upload(client, admin_token, os_criada["id"])
    data = resp.json()["data"]
    assert data["versao"] == 2


def test_extensao_executavel_bloqueada(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte",
        headers=auth(client, admin_token),
        files={"arquivo": ("virus.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "não é permitida" in resp.json()["detail"]


def test_arquivo_vazio_rejeitado(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte",
        headers=auth(client, admin_token),
        files={"arquivo": ("vazio.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------- decisão


def test_estado_sem_arte(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = client.get(
        f"/v1/os/{os_criada['id']}/arte", headers=auth(client, admin_token)
    )
    data = resp.json()
    assert data["data"] == []
    assert data["estado"] == "sem_arte"


def test_estado_aguardando_aprovacao(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    _upload(client, admin_token, os_criada["id"])
    resp = client.get(
        f"/v1/os/{os_criada['id']}/arte", headers=auth(client, admin_token)
    )
    assert resp.json()["estado"] == "aguardando_aprovacao"


def test_aprovar_arte_muda_estado_para_aprovada(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    upload = _upload(client, admin_token, os_criada["id"]).json()["data"]
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/{upload['id']}/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "aprovada"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["decisao"] == "aprovada"

    estado = client.get(
        f"/v1/os/{os_criada['id']}/arte", headers=auth(client, admin_token)
    ).json()["estado"]
    assert estado == "aprovada"


def test_ajuste_arte_registra_comentarios_e_estado(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    upload = _upload(client, admin_token, os_criada["id"]).json()["data"]
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/{upload['id']}/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "ajuste", "comentarios": "Trocar o logo para versão horizontal"},
    )
    assert resp.status_code == 201, resp.text
    assert "logo" in resp.json()["data"]["comentarios"]

    estado = client.get(
        f"/v1/os/{os_criada['id']}/arte", headers=auth(client, admin_token)
    ).json()["estado"]
    assert estado == "ajuste_solicitado"


def test_ajuste_sem_comentarios_e_recusado(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    upload = _upload(client, admin_token, os_criada["id"]).json()["data"]
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/{upload['id']}/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "ajuste"},  # sem comentarios
    )
    assert resp.status_code == 400


def test_decisao_em_versao_inexistente_404(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/99999/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "aprovada"},
    )
    assert resp.status_code == 404


# -------------------------------------------------------------- link público


def test_link_prova_gera_token_com_expiracao(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/link",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data["token"]) > 20
    assert data["tipo"] == "prova"
    # expira no futuro
    expira = datetime.fromisoformat(data["expira_em"].replace("Z", "+00:00"))
    assert expira > datetime.now(expira.tzinfo)


# ------------------------------------------------------------------ modelo


def test_hash_sha256_consistente(client, admin_token):
    """O hash gravado bate com o hash calculado do conteúdo enviado."""
    import hashlib

    conteudo = b"conteudo de teste para hash"
    os_criada = _criar_os(client, admin_token)
    resp = _upload(
        client, admin_token, os_criada["id"], conteudo=io.BytesIO(conteudo)
    )
    data = resp.json()["data"]
    assert data["hash_sha256"] == hashlib.sha256(conteudo).hexdigest()


# ------------------------------------------- status da OS incorpora a arte (§3.5)


def test_upload_muda_status_para_aguardando_aprovacao(client, admin_token):
    """OS aberta + upload → "Aguardando aprovação" (§3.5)."""
    os_criada = _criar_os(client, admin_token)
    assert os_criada["status"] == "aberto"
    _upload(client, admin_token, os_criada["id"])
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "aguardando_aprovacao"


def test_decisao_ajuste_volta_status_para_aguardando_arte(client, admin_token):
    """Cliente pede ajuste → OS volta a "Aguardando arte" (§3.5)."""
    os_criada = _criar_os(client, admin_token)
    versao = _upload(client, admin_token, os_criada["id"]).json()["data"]
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/{versao['id']}/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "ajuste", "comentarios": "Fonte maior"},
    )
    assert resp.status_code == 201, resp.text
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "aguardando_arte"

    # reenvio da arte corrigida: volta a aguardar a aprovação
    _upload(client, admin_token, os_criada["id"])
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "aguardando_aprovacao"


def test_decisao_aprovada_muda_status_para_aprovado(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    versao = _upload(client, admin_token, os_criada["id"]).json()["data"]
    resp = client.post(
        f"/v1/os/{os_criada['id']}/arte/{versao['id']}/decisao",
        headers=auth(client, admin_token),
        json={"decisao": "aprovada"},
    )
    assert resp.status_code == 201, resp.text
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "aprovado"


def test_status_manual_aguardando_arte(client, admin_token):
    """O operador pode sinalizar "aguardando arte do cliente" manualmente."""
    os_criada = _criar_os(client, admin_token)
    resp = client.patch(
        f"/v1/os/{os_criada['id']}/status", headers=auth(client, admin_token),
        json={"status": "aguardando_arte"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "aguardando_arte"


def test_producao_sem_arte_aprovada_409(client, admin_token):
    """§3.5: não inicia produção sem arte aprovada."""
    os_criada = _criar_os(client, admin_token)
    resp = client.patch(
        f"/v1/os/{os_criada['id']}/status", headers=auth(client, admin_token),
        json={"status": "producao"},
    )
    assert resp.status_code == 409, resp.text
    assert "arte aprovada" in resp.json()["detail"].lower()

    # arte pendente (sem decisão) também bloqueia
    _upload(client, admin_token, os_criada["id"])
    resp = client.patch(
        f"/v1/os/{os_criada['id']}/status", headers=auth(client, admin_token),
        json={"status": "producao"},
    )
    assert resp.status_code == 409, resp.text


def test_producao_com_arte_aprovada_200(client, admin_token):
    os_criada = _criar_os(client, admin_token)
    arte_aprovada(client, admin_token, os_criada["id"])
    resp = client.patch(
        f"/v1/os/{os_criada['id']}/status", headers=auth(client, admin_token),
        json={"status": "producao"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "producao"


def test_reenvio_nao_regrede_status_avancado(client, admin_token):
    """OS já em produção não volta a "aguardando" em reenvios de arte."""
    os_criada = _criar_os(client, admin_token)
    arte_aprovada(client, admin_token, os_criada["id"])
    client.patch(
        f"/v1/os/{os_criada['id']}/status", headers=auth(client, admin_token),
        json={"status": "producao"},
    )
    _upload(client, admin_token, os_criada["id"])  # ajuste tardio
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "producao"
