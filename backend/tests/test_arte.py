"""Arte, prova e aprovação (M3, PRD v3.0 §3.5).

Cobre: upload de versões (v1, v2…), decisão do cliente (aprovada / ajuste
com comentários), estado derivado da arte, link público com token/expiração,
e validações (extensão bloqueada, arquivo vazio, ajuste sem comentários).
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.main import app
from app.models.movimento import ArteAprovacao, ArteVersao, LinkPublico
from app.models.enums import DecisaoArte
from app.db import SessionLocal
from tests.conftest import TEST_DB_URL, auth

client = TestClient(app)


@pytest.fixture()
def db_teste():
    engine = create_engine(TEST_DB_URL)
    with Session(engine) as sessao:
        yield sessao
    engine.dispose()


@pytest.fixture()
def _filial(db_teste) -> int:
    return int(
        db_teste.execute(text("SELECT id FROM filial ORDER BY id LIMIT 1")).scalar_one()
    )


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
