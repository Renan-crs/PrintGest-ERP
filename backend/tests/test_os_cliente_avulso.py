"""Fase 2 — cliente não cadastrado em O.S./orçamento."""

import uuid

from app.db import SessionLocal
from app.models.movimento import OrdemServico
from tests.conftest import auth


def _u():
    return uuid.uuid4().hex[:6]


def _item():
    return [{
        "descricao_avulsa": "Serviço avulso", "quantidade": "1",
        "valor_unitario": "100.00", "desconto": "0",
    }]


def test_criar_os_com_cliente_avulso(client, admin_token):
    h = auth(client, admin_token)
    nome = f"Cliente Avulso {_u()}"
    r = client.post(
        "/v1/os",
        headers=h,
        json={
            "tipo": "os",
            "cliente_nome_avulso": nome,
            "itens": _item(),
        },
    )
    assert r.status_code == 200, r.text
    dado = r.json()["data"]
    assert dado["cliente_id"] is None
    assert dado["cliente_nome_avulso"] == nome
    assert dado["cliente_nome"] is None

    os_id = dado["id"]
    det = client.get(f"/v1/os/{os_id}", headers=h).json()["data"]
    assert det["cliente_nome_avulso"] == nome


def test_validacao_cliente_ou_avulso(client, admin_token):
    h = auth(client, admin_token)
    sem = client.post(
        "/v1/os", headers=h, json={"itens": _item()}
    )
    assert sem.status_code == 422

    # Cliente cadastrado + avulso ao mesmo tempo → 422
    cli = client.post(
        "/v1/clientes",
        headers=h,
        json={"nome_razao": f"Cliente {_u()}", "tipo_pessoa": "pf"},
    ).json()["data"]
    ambos = client.post(
        "/v1/os",
        headers=h,
        json={
            "cliente_id": cli["id"],
            "cliente_nome_avulso": "Outro nome",
            "itens": _item(),
        },
    )
    assert ambos.status_code == 422


def test_busca_q_encontra_avulso(client, admin_token):
    h = auth(client, admin_token)
    nome = f"AvulsoBusca{_u()}"
    r = client.post(
        "/v1/os",
        headers=h,
        json={"cliente_nome_avulso": nome, "itens": _item()},
    )
    assert r.status_code == 200, r.text
    os_id = r.json()["data"]["id"]

    lista = client.get(
        "/v1/os", headers=h, params={"q": nome}
    ).json()["data"]
    assert any(o["id"] == os_id for o in lista)


def test_conversao_orcamento_avulso_preserva_nome(client, admin_token):
    h = auth(client, admin_token)
    nome = f"OrcAvulso{_u()}"
    r = client.post(
        "/v1/os",
        headers=h,
        json={
            "tipo": "orcamento",
            "cliente_nome_avulso": nome,
            "itens": _item(),
        },
    )
    assert r.status_code == 200, r.text
    orc_id = r.json()["data"]["id"]

    conv = client.post(f"/v1/os/{orc_id}/converter", headers=h)
    assert conv.status_code == 200, conv.text
    os_obj = conv.json()["data"]
    assert os_obj["cliente_nome_avulso"] == nome
    assert os_obj["cliente_id"] is None
