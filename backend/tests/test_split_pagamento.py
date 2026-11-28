"""Split payment — múltiplas formas de pagamento na mesma venda."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import auth
from tests.test_vendas import _criar_produto, _entrada


def _venda(client, token, produto_id, **extra):
    _entrada(client, token, produto_id, 10)
    payload = {
        "forma_pagamento": "dinheiro",
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": 1,
                "valor_unitario": "100.00",
            }
        ],
    }
    payload.update(extra)
    return client.post("/v1/vendas", headers=auth(client, token), json=payload)


def test_split_dinheiro_mais_pix(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    resp = _venda(
        client,
        admin_token,
        produto["id"],
        pagamentos=[
            {"forma_pagamento": "dinheiro", "valor": "40.00", "valor_recebido": "50.00"},
            {"forma_pagamento": "pix", "valor": "60.00"},
        ],
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert dados["valor_total"] == "100.00"
    assert dados["forma_pagamento"] == "dinheiro"  # compatibilidade
    assert [(p["forma_pagamento"], p["valor"]) for p in dados["pagamentos"]] == [
        ("dinheiro", "40.00"), ("pix", "60.00")
    ]

    detalhe = client.get(
        f"/v1/vendas/{dados['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert len(detalhe["pagamentos"]) == 2
    # Rastreabilidade: split cobre o total, então não há sinal nem saldo.
    assert detalhe["valor_sinal"] == "0.00"
    assert detalhe["saldo"] == "0.00"
    assert detalhe["lancamentos"] == []


def test_recebido_menor_que_total_expoe_saldo(client, admin_token, caixa_admin):
    """Ex.: produto de 120 com 60 recebidos — o saldo aparece no detalhe."""
    produto = _criar_produto(client, admin_token)
    resp = _venda(
        client,
        admin_token,
        produto["id"],
        itens=[
            {
                "produto_id": produto["id"],
                "quantidade": 1,
                "valor_unitario": "120.00",
            }
        ],
        valor_recebido="60.00",
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert dados["valor_total"] == "120.00"
    assert dados["valor_recebido"] == "60.00"
    assert dados["saldo"] == "60.00"
    assert dados["valor_sinal"] == "0.00"
    assert dados["lancamentos"] == []


def test_split_soma_divergente_e_rejeitada(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    resp = _venda(
        client,
        admin_token,
        produto["id"],
        pagamentos=[
            {"forma_pagamento": "dinheiro", "valor": "40.00"},
            {"forma_pagamento": "pix", "valor": "50.00"},
        ],
    )
    assert resp.status_code == 400
    assert "soma das formas" in resp.json()["detail"].lower()


def test_split_mais_de_dez_formas_e_rejeitado(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    resp = _venda(
        client,
        admin_token,
        produto["id"],
        pagamentos=[
            {"forma_pagamento": "pix", "valor": "10.00"} for _ in range(11)
        ],
    )
    assert resp.status_code == 400


def test_sem_pagamentos_continua_legado(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    resp = _venda(client, admin_token, produto["id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["pagamentos"] == []


def test_split_fiado_gera_saldo_devedor(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    cliente = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Cliente Split", "tipo_pessoa": "pf"},
    ).json()["data"]
    resp = _venda(
        client,
        admin_token,
        produto["id"],
        cliente_id=cliente["id"],
        pagamentos=[
            {"forma_pagamento": "pix", "valor": "60.00"},
            {"forma_pagamento": "fiado", "valor": "40.00"},
        ],
    )
    assert resp.status_code == 200, resp.text
    contas = client.get(
        "/v1/financeiro/contas-receber", headers=auth(client, admin_token)
    )
    assert contas.status_code == 200
    assert any(
        Decimal(c["valor"]) == Decimal("40.00") for c in contas.json()["data"]
    )
