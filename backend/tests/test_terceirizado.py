"""Rastreio de terceirizados na OS (M4, PRD v3.0 §3.6).

Cobre o ciclo: envio automático na seleção da cotação → retorno → conferência
(ok / refação) → alerta de atraso quando a previsão vence sem retorno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from tests.conftest import auth


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_cliente(client, token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, token),
        json={"nome_razao": f"Cliente Terceirizado {_u()}", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_fornecedor(client, token):
    resp = client.post(
        "/v1/fornecedores",
        headers=auth(client, token),
        json={"nome_razao": f"Fornecedor {_u()}", "tipo_pessoa": "pj"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_os_com_item_fornecedor(client, token, cliente):
    resp = client.post(
        "/v1/os",
        headers=auth(client, token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "produto_id": None,
                    "descricao_avulsa": "Hot stamping terceirizado",
                    "quantidade": 1,
                    "valor_unitario": 0,
                    "tipo": "fornecedor",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"], resp.json()["data"]["itens"][0]


def _selecionar_cotacao(client, token, os_id, item_id, fornecedor_id, vf, prazo_dias=5):
    """Lança e seleciona a cotação — dispara o rastreio de terceirizado."""
    resp = client.post(
        f"/v1/os/{os_id}/itens/{item_id}/cotacoes",
        headers=auth(client, token),
        json={
            "fornecedor_id": fornecedor_id,
            "vf": vf,
            "prazo_dias": prazo_dias,
            "selecionada": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ------------------------------------------------------------------ ciclo


def test_selecao_de_cotacao_cria_rastreio_automatico(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)

    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "100.00", prazo_dias=7
    )

    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["data_envio"] == date.today().isoformat()
    assert data["previsao_retorno"] == (date.today() + timedelta(days=7)).isoformat()
    assert data["data_retorno"] is None
    assert data["conferencia"] == "pendente"
    assert data["atrasado"] is False
    assert "Hot stamping" in data["descricao_item"]


def test_receber_e_conferir_ok(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "50.00", prazo_dias=3
    )

    # 1. receber
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/receber",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["data_retorno"] == date.today().isoformat()
    assert data["conferencia"] == "pendente"

    # 2. conferir: ok
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/conferir",
        headers=auth(client, admin_token),
        json={"conferencia": "ok"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["conferencia"] == "ok"
    assert data["atrasado"] is False


def test_conferir_refacao_registra_motivo(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "80.00"
    )
    client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/receber",
        headers=auth(client, admin_token),
    )
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/conferir",
        headers=auth(client, admin_token),
        json={"conferencia": "refacao", "observacoes": "Cor desbotada — refazer"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["conferencia"] == "refacao"
    assert "desbotada" in data["observacoes"]


def test_receber_duas_vezes_e_recusado(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "30.00"
    )
    client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/receber",
        headers=auth(client, admin_token),
    )
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/receber",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 409


def test_conferir_sem_retorno_e_recusado(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "30.00"
    )
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/conferir",
        headers=auth(client, admin_token),
        json={"conferencia": "ok"},
    )
    assert resp.status_code == 409


def test_item_sem_rastreio_responde_404(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 404
    assert "selecione a cotação" in resp.json()["detail"].lower()


def test_atrasado_quando_previsao_vence_sem_retorno(client, admin_token):
    """Previsão no passado + sem retorno = atrasado (para o sino/dashboard)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from tests.conftest import TEST_DB_URL

    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _selecionar_cotacao(
        client, admin_token, os_criada["id"], item["id"], fornecedor["id"], "60.00", prazo_dias=1
    )

    # Força envio e previsão para o passado (simula passagem de tempo)
    engine = create_engine(TEST_DB_URL)
    with Session(engine) as db:
        db.execute(
            text(
                "UPDATE os_terceirizado "
                "SET data_envio = CURRENT_DATE - 2, previsao_retorno = CURRENT_DATE - 1 "
                "WHERE item_id = :item"
            ),
            {"item": item["id"]},
        )
        db.commit()
    engine.dispose()

    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado",
        headers=auth(client, admin_token),
    )
    data = resp.json()["data"]
    assert data["atrasado"] is True

    # Receber resolve o atraso
    client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado/receber",
        headers=auth(client, admin_token),
    )
    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/terceirizado",
        headers=auth(client, admin_token),
    )
    assert resp.json()["data"]["atrasado"] is False
