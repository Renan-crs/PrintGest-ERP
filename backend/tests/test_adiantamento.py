"""Pagamento adiantado / sinal do cliente (tela 2.1).

Um cliente pode exigir recebimento antecipado (100% ou um sinal percentual) ao
abrir O.S. e venda de balcão. Sem confirmação o documento é recusado (400) e a
transação é revertida; com confirmação grava-se o lançamento financeiro
(`conta_receber` baixada e, havendo caixa aberto, `movimento_caixa`).
Orçamentos são gratuitos.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.conftest import TEST_DB_URL, auth


def _u() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def db_teste():
    engine = create_engine(TEST_DB_URL)
    with Session(engine) as sessao:
        yield sessao
    engine.dispose()


def _criar_cliente(client, token, **extra):
    payload = {"nome_razao": f"Cliente Adto {_u()}", "tipo_pessoa": "pf"}
    payload.update(extra)
    resp = client.post("/v1/clientes", headers=auth(client, token), json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _item(quantidade=1, valor=100.0):
    return {
        "produto_id": None,
        "descricao_avulsa": "Corte e vinco",
        "quantidade": quantidade,
        "valor_unitario": valor,
    }


def _criar_os(client, token, cliente_id, *, tipo="os", confirmado=False, itens=None):
    return client.post(
        "/v1/os",
        headers=auth(client, token),
        json={
            "tipo": tipo,
            "cliente_id": cliente_id,
            "pagamento_confirmado": confirmado,
            "itens": itens or [_item()],
        },
    )


def _produto_com_estoque(client, token, quantidade=5):
    codigo = f"AD{uuid.uuid4().hex[:8].upper()}"
    prod = client.post(
        "/v1/produtos",
        headers=auth(client, token),
        json={"codigo": codigo, "nome": "Banner Adto", "preco_venda": 100.0},
    )
    assert prod.status_code == 200, prod.text
    produto_id = prod.json()["data"]["id"]
    mov = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, token),
        json={"produto_id": produto_id, "tipo": "entrada", "quantidade": quantidade},
    )
    assert mov.status_code == 200, mov.text
    return produto_id


def _contas_os(db, os_id):
    return db.execute(
        text(
            "SELECT valor, valor_pago, status FROM conta_receber "
            "WHERE ordem_servico_id = :id"
        ),
        {"id": os_id},
    ).all()


# --- Cadastro do cliente --------------------------------------------------------


def test_cliente_nao_pode_ser_adiantado_e_sinal(client, admin_token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={
            "nome_razao": f"Conflito {_u()}",
            "pagamento_adiantado": True,
            "sinal": True,
        },
    )
    assert resp.status_code == 422


def test_cliente_sinal_pct_fora_da_faixa_422(client, admin_token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": f"Pct {_u()}", "sinal": True, "sinal_pct": 150},
    )
    assert resp.status_code == 422


def test_cliente_retorna_condicao_de_pagamento(client, admin_token):
    cliente = _criar_cliente(client, admin_token, sinal=True, sinal_pct=35)
    assert cliente["sinal"] is True
    assert cliente["pagamento_adiantado"] is False
    assert Decimal(cliente["sinal_pct"]) == Decimal("35.00")


# --- O.S. -----------------------------------------------------------------------


def test_os_adiantado_bloqueia_sem_confirmar_e_reverte(client, admin_token, db_teste):
    cliente = _criar_cliente(client, admin_token, pagamento_adiantado=True)
    resp = _criar_os(client, admin_token, cliente["id"])
    assert resp.status_code == 400, resp.text
    assert "adiantado" in resp.json()["detail"].lower()
    # A transação foi revertida: nenhuma O.S. persistida para o cliente.
    total = db_teste.execute(
        text("SELECT count(*) FROM ordem_servico WHERE cliente_id = :id"),
        {"id": cliente["id"]},
    ).scalar_one()
    assert total == 0


def test_os_adiantado_confirmado_cria_conta_paga(client, admin_token, db_teste):
    cliente = _criar_cliente(client, admin_token, pagamento_adiantado=True)
    resp = _criar_os(client, admin_token, cliente["id"], confirmado=True)
    assert resp.status_code == 200, resp.text
    os_id = resp.json()["data"]["id"]

    linhas = _contas_os(db_teste, os_id)
    assert len(linhas) == 1
    valor, pago, status_conta = linhas[0]
    assert Decimal(valor) == Decimal("100.00")
    assert Decimal(pago) == Decimal("100.00")
    assert status_conta == "paga"


def test_os_sinal_usa_percentual_do_cliente(client, admin_token, db_teste):
    cliente = _criar_cliente(client, admin_token, sinal=True, sinal_pct=30)
    resp = _criar_os(
        client, admin_token, cliente["id"], confirmado=True,
        itens=[_item(quantidade=1, valor=200.0)],
    )
    assert resp.status_code == 200, resp.text
    linhas = _contas_os(db_teste, resp.json()["data"]["id"])
    assert len(linhas) == 1
    assert Decimal(linhas[0][0]) == Decimal("60.00")


def test_os_sinal_bloqueia_sem_confirmar(client, admin_token):
    cliente = _criar_cliente(client, admin_token, sinal=True, sinal_pct=50)
    resp = _criar_os(client, admin_token, cliente["id"])
    assert resp.status_code == 400, resp.text
    assert "sinal" in resp.json()["detail"].lower()


def test_orcamento_nao_exige_pagamento(client, admin_token):
    cliente = _criar_cliente(client, admin_token, pagamento_adiantado=True)
    resp = _criar_os(client, admin_token, cliente["id"], tipo="orcamento")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["tipo"] == "orcamento"


def test_converter_orcamento_exige_pagamento(client, admin_token, db_teste):
    cliente = _criar_cliente(client, admin_token, pagamento_adiantado=True)
    orc = _criar_os(
        client, admin_token, cliente["id"], tipo="orcamento",
        itens=[_item(quantidade=1, valor=50.0)],
    )
    assert orc.status_code == 200, orc.text
    orc_id = orc.json()["data"]["id"]

    bloqueado = client.post(
        f"/v1/os/{orc_id}/converter", headers=auth(client, admin_token)
    )
    assert bloqueado.status_code == 400, bloqueado.text
    assert "adiantado" in bloqueado.json()["detail"].lower()

    ok = client.post(
        f"/v1/os/{orc_id}/converter",
        headers=auth(client, admin_token),
        json={"pagamento_confirmado": True},
    )
    assert ok.status_code == 200, ok.text
    assert len(_contas_os(db_teste, ok.json()["data"]["id"])) == 1


# --- Venda de balcão ------------------------------------------------------------


def test_venda_sinal_bloqueia_e_confirmada_cria_conta(client, admin_token, db_teste, caixa_admin):
    cliente = _criar_cliente(client, admin_token, sinal=True, sinal_pct=50)
    produto_id = _produto_com_estoque(client, admin_token, 5)
    payload = {
        "forma_pagamento": "dinheiro",
        "cliente_id": cliente["id"],
        "itens": [
            {"produto_id": produto_id, "quantidade": 1, "valor_unitario": 100.0}
        ],
    }

    sem = client.post("/v1/vendas", headers=auth(client, admin_token), json=payload)
    assert sem.status_code == 400, sem.text
    assert "sinal" in sem.json()["detail"].lower()
    # Sem confirmação nada é persistido nem baixado.
    saldo = db_teste.execute(
        text("SELECT saldo FROM produto_estoque WHERE produto_id = :id"),
        {"id": produto_id},
    ).scalar_one()
    assert Decimal(saldo) == Decimal("5")

    com = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={**payload, "pagamento_confirmado": True},
    )
    assert com.status_code == 200, com.text
    venda_id = com.json()["data"]["id"]
    linhas = db_teste.execute(
        text("SELECT valor, status FROM conta_receber WHERE venda_balcao_id = :id"),
        {"id": venda_id},
    ).all()
    assert len(linhas) == 1
    assert Decimal(linhas[0][0]) == Decimal("50.00")
    assert linhas[0][1] == "paga"


def test_confirmacao_gera_movimento_de_caixa_com_caixa_aberto(
    client, admin_token, db_teste
):
    uid = db_teste.execute(
        text("SELECT id FROM usuario WHERE login = 'admin'")
    ).scalar_one()
    cliente = _criar_cliente(client, admin_token, pagamento_adiantado=True)
    db_teste.execute(
        text(
            "INSERT INTO caixa (filial_id, usuario_id, valor_abertura) "
            "VALUES (1, :uid, 0)"
        ),
        {"uid": uid},
    )
    db_teste.commit()
    try:
        resp = _criar_os(
            client, admin_token, cliente["id"], confirmado=True,
            itens=[_item(quantidade=1, valor=80.0)],
        )
        assert resp.status_code == 200, resp.text
        os_id = resp.json()["data"]["id"]
        mov = db_teste.execute(
            text(
                "SELECT m.valor, m.tipo FROM movimento_caixa m "
                "JOIN conta_receber c ON c.id = m.conta_receber_id "
                "WHERE c.ordem_servico_id = :id"
            ),
            {"id": os_id},
        ).all()
        assert len(mov) == 1
        assert Decimal(mov[0][0]) == Decimal("80.00")
        assert mov[0][1] == "entrada"
    finally:
        db_teste.execute(
            text(
                "DELETE FROM movimento_caixa WHERE caixa_id IN "
                "(SELECT id FROM caixa WHERE usuario_id = :uid)"
            ),
            {"uid": uid},
        )
        db_teste.execute(
            text("DELETE FROM caixa WHERE usuario_id = :uid"), {"uid": uid}
        )
        db_teste.commit()
