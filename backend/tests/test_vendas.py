"""Venda de Balcão (PDV) — PRD v2.0 §2.2.

Cobre baixa/estorno de estoque na mesma transação, kardex com origem
`venda_balcao`, busca por cliente/número (regressão do `NameError` em
`venda_service.listar`) e integridade referencial (FK inválida → 409).
"""

import uuid
from decimal import Decimal

from tests.conftest import auth


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_produto(client, admin_token, **extra):
    payload = {
        "codigo": f"VD{uuid.uuid4().hex[:8].upper()}",
        "nome": "Papel Sulfite A4",
        "tipo": "produto",
        "unidade": "resma",
        "preco_custo": 10.0,
        "preco_venda": 20.0,
        "estoque_minimo": 1,
    }
    payload.update(extra)
    resp = client.post("/v1/produtos", headers=auth(client, admin_token), json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _entrada(client, admin_token, produto_id, quantidade):
    resp = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, admin_token),
        json={"produto_id": produto_id, "tipo": "entrada", "quantidade": quantidade},
    )
    assert resp.status_code == 200, resp.text


def _criar_cliente(client, admin_token, nome=None):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": nome or f"Cliente {_u()}", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _vender(client, admin_token, produto_id, quantidade=1, **extra):
    payload = {
        "forma_pagamento": "dinheiro",
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": quantidade,
                "valor_unitario": 20.0,
            }
        ],
    }
    payload.update(extra)
    return client.post("/v1/vendas", headers=auth(client, admin_token), json=payload)


def _saldo(client, admin_token, produto_id) -> Decimal:
    resp = client.get("/v1/estoque", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    linha = next(i for i in resp.json()["data"] if i["produto_id"] == produto_id)
    return Decimal(linha["saldo"])


def test_venda_baixa_estoque_e_registra_kardex(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    resp = _vender(client, admin_token, produto["id"], quantidade=3)
    assert resp.status_code == 200, resp.text
    venda = resp.json()["data"]
    assert venda["status"] == "ok"
    assert Decimal(venda["valor_total"]) == Decimal("60.00")
    assert _saldo(client, admin_token, produto["id"]) == Decimal("7")

    kardex = client.get(
        f"/v1/estoque/{produto['id']}/kardex", headers=auth(client, admin_token)
    )
    assert kardex.status_code == 200, kardex.text
    mov = kardex.json()["data"][0]
    assert mov["origem"] == "venda_balcao"
    assert mov["tipo"] == "saida"
    assert mov["documento_id"] == venda["id"]
    assert Decimal(mov["quantidade"]) == Decimal("3")


# --- M0 (PRD v3.0 §2): o PDV não opera com caixa fechado --------------------------


def test_venda_com_caixa_fechado_e_recusada(client, admin_token):
    """Sem caixa aberto para o vendedor logado: 409 com orientação clara."""
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    resp = _vender(client, admin_token, produto["id"])
    assert resp.status_code == 409, resp.text
    assert "Caixa fechado" in resp.json()["detail"]
    # Nada foi persistido: o estoque segue intacto.
    assert _saldo(client, admin_token, produto["id"]) == Decimal("10")


def test_venda_com_caixa_aberto_passa(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    resp = _vender(client, admin_token, produto["id"])
    assert resp.status_code == 200, resp.text
    assert str(caixa_admin.status.value) == "aberto"


def test_venda_estoque_insuficiente_409(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 1)

    resp = _vender(client, admin_token, produto["id"], quantidade=5)
    assert resp.status_code == 409, resp.text
    assert "insuficiente" in resp.json()["detail"].lower()
    # A transação é revertida: o saldo permanece intacto.
    assert _saldo(client, admin_token, produto["id"]) == Decimal("1")


def test_cancelar_venda_estorna_estoque(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)
    venda = _vender(client, admin_token, produto["id"], quantidade=4).json()["data"]
    assert _saldo(client, admin_token, produto["id"]) == Decimal("6")

    resp = client.delete(f"/v1/vendas/{venda['id']}", headers=auth(client, admin_token))
    assert resp.status_code == 204, resp.text
    assert _saldo(client, admin_token, produto["id"]) == Decimal("10")


def test_venda_busca_por_cliente_e_numero(client, admin_token, caixa_admin):
    """Regressão: `GET /v1/vendas?q=` estourava NameError (String/cliente_nome)."""
    cliente = _criar_cliente(client, admin_token, nome=f"Gráfica Rápida {_u()}")
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 5)
    venda = _vender(client, admin_token, produto["id"], cliente_id=cliente["id"]).json()[
        "data"
    ]

    por_nome = client.get(
        "/v1/vendas",
        params={"q": cliente["nome_razao"]},
        headers=auth(client, admin_token),
    )
    assert por_nome.status_code == 200, por_nome.text
    assert venda["id"] in [v["id"] for v in por_nome.json()["data"]]

    por_numero = client.get(
        "/v1/vendas",
        params={"q": str(venda["numero"])},
        headers=auth(client, admin_token),
    )
    assert por_numero.status_code == 200, por_numero.text
    assert venda["id"] in [v["id"] for v in por_numero.json()["data"]]


def test_venda_cliente_inexistente_409(client, admin_token, caixa_admin):
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 3)
    resp = _vender(client, admin_token, produto["id"], cliente_id=999999)
    assert resp.status_code == 409, resp.text
    # Nada é persistido nem baixado quando a FK é inválida.
    assert _saldo(client, admin_token, produto["id"]) == Decimal("3")
