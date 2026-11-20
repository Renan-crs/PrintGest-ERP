"""Cenários financeiros reais: caixa sem movimento, sinal já pago, restante,
FIADO, parcelamento e baixa com movimento de caixa.
"""

import uuid
from decimal import Decimal

import pytest

from app.db import SessionLocal
from app.models.cadastros import Cliente
from app.models.financeiro import Caixa, ContaReceber, MovimentoCaixa
from app.models.movimento import VendaBalcao
from tests.conftest import auth
from tests.test_vendas import _criar_produto, _entrada, _vender


@pytest.fixture(autouse=True)
def _limpar(client):
    def limpar():
        db = SessionLocal()
        try:
            db.query(MovimentoCaixa).delete()
            db.query(ContaReceber).delete()
            db.query(VendaBalcao).update({VendaBalcao.caixa_id: None})
            db.query(VendaBalcao).delete()
            db.query(Caixa).delete()
            db.commit()
        finally:
            db.close()

    limpar()
    yield
    limpar()


def _u():
    return uuid.uuid4().hex[:8]


def _abrir(client, token, valor=0):
    r = client.post(
        "/v1/financeiro/caixa/abrir",
        headers=auth(client, token),
        json={"valor_abertura": valor},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _vender_100(client, token, produto_id, **extra):
    """Venda de R$ 100 (o helper padrão de test_vendas usa R$ 20)."""
    itens = [{"produto_id": produto_id, "quantidade": 1, "valor_unitario": 100}]
    extra.setdefault("itens", itens)
    return _vender(client, token, produto_id, **extra)


def _cliente(client, token, **extra):
    corpo = {"nome_razao": f"Cliente {_u()}", "tipo_pessoa": "pf"}
    corpo.update(extra)
    r = client.post("/v1/clientes", headers=auth(client, token), json=corpo)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _contas(cliente_id=None):
    db = SessionLocal()
    try:
        q = db.query(ContaReceber)
        if cliente_id is not None:
            q = q.filter(ContaReceber.cliente_id == cliente_id)
        return [
            {
                "valor": c.valor,
                "pago": c.valor_pago,
                "status": c.status.value,
                "parcela": c.parcela,
                "total": c.total_parcelas,
            }
            for c in q.all()
        ]
    finally:
        db.close()


def _movimentos(caixa_id):
    db = SessionLocal()
    try:
        return [
            {"tipo": m.tipo.value, "valor": m.valor, "conta_id": m.conta_receber_id}
            for m in db.query(MovimentoCaixa).filter(
                MovimentoCaixa.caixa_id == caixa_id
            ).all()
        ]
    finally:
        db.close()


def test_fechar_caixa_sem_valor_informado_usa_esperado(client, admin_token):
    h = auth(client, admin_token)
    caixa = _abrir(client, admin_token, valor=0)
    r = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar", headers=h, json={}
    )
    assert r.status_code == 200, r.text
    dado = r.json()["data"]
    assert Decimal(dado["valor_esperado"]) == 0
    assert Decimal(dado["valor_informado"]) == 0
    assert Decimal(dado["diferenca"]) == 0

    # Com movimento: informado omitido adota o esperado (100 + 20).
    caixa = _abrir(client, admin_token, valor=100)
    client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=h, json={"tipo": "suprimento", "valor": 20},
    )
    r = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar", headers=h, json={}
    )
    assert r.status_code == 200, r.text
    dado = r.json()["data"]
    assert Decimal(dado["valor_informado"]) == Decimal("120.00")
    assert Decimal(dado["diferenca"]) == 0


def test_venda_com_sinal_nao_duplica_entrada_no_caixa(client, admin_token):
    cliente = _cliente(client, admin_token, sinal=True, sinal_pct=50)
    caixa = _abrir(client, admin_token)
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    r = _vender_100(
        client, admin_token, produto["id"], quantidade=1,
        cliente_id=cliente["id"], pagamento_confirmado=True,
    )
    assert r.status_code == 200, r.text
    movs = _movimentos(caixa["id"])
    assert sorted(Decimal(m["valor"]) for m in movs) == [Decimal("50.00"), Decimal("50.00")]
    assert sum((Decimal(m["valor"]) for m in movs), Decimal(0)) == Decimal("100.00")

    # O restante foi pago no balcão (dinheiro): só o sinal vira título, já pago.
    contas = _contas(cliente["id"])
    assert [(Decimal(c["valor"]), c["status"]) for c in contas] == [
        (Decimal("50.00"), "paga")
    ]


def test_venda_fiado_gera_conta_aberta_sem_entrada_no_caixa(client, admin_token):
    cliente = _cliente(client, admin_token)
    caixa = _abrir(client, admin_token)
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    r = _vender_100(
        client, admin_token, produto["id"],
        cliente_id=cliente["id"], forma_pagamento="fiado",
    )
    assert r.status_code == 200, r.text
    assert _movimentos(caixa["id"]) == []
    contas = _contas(cliente["id"])
    assert len(contas) == 1
    assert Decimal(contas[0]["valor"]) == Decimal("100.00")
    assert contas[0]["status"] == "aberta"


def test_venda_boleto_parcelada_gera_titulos(client, admin_token):
    cliente = _cliente(client, admin_token)
    _abrir(client, admin_token)
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    r = _vender_100(
        client, admin_token, produto["id"],
        cliente_id=cliente["id"], forma_pagamento="boleto", parcelas=3,
    )
    assert r.status_code == 200, r.text
    contas = sorted(_contas(cliente["id"]), key=lambda c: c["parcela"])
    assert [c["parcela"] for c in contas] == [1, 2, 3]
    assert [c["total"] for c in contas] == [3, 3, 3]
    assert sum((Decimal(c["valor"]) for c in contas), Decimal(0)) == Decimal("100.00")
    assert all(c["status"] == "aberta" for c in contas)


def test_os_com_sinal_deixa_restante_a_receber(client, admin_token):
    cliente = _cliente(client, admin_token, sinal=True, sinal_pct=30)
    r = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "cliente_id": cliente["id"],
            "pagamento_confirmado": True,
            "itens": [{"descricao_avulsa": "Serviço", "quantidade": 1, "valor_unitario": 200}],
        },
    )
    assert r.status_code == 200, r.text
    os_dado = r.json()["data"]
    assert Decimal(str(os_dado["valor_sinal"])) == Decimal("60.00")
    assert Decimal(str(os_dado["saldo"])) == Decimal("140.00")
    contas = _contas(cliente["id"])
    assert [(Decimal(c["valor"]), c["status"]) for c in contas] == [
        (Decimal("60.00"), "paga"), (Decimal("140.00"), "aberta")
    ]


def test_baixa_de_conta_gera_movimento_no_caixa(client, admin_token):
    cliente = _cliente(client, admin_token)
    caixa = _abrir(client, admin_token)
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)
    venda = _vender_100(
        client, admin_token, produto["id"],
        cliente_id=cliente["id"], forma_pagamento="fiado",
    ).json()["data"]
    # Busca o id pelo ORM (as contas criadas não expõem id no helper).
    db = SessionLocal()
    try:
        conta_id = db.query(ContaReceber).first().id
    finally:
        db.close()

    h = auth(client, admin_token)
    r = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa",
        headers=h, json={"valor_pago": 40},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "aberta"  # parcial
    movs = _movimentos(caixa["id"])
    assert len(movs) == 1
    assert Decimal(movs[0]["valor"]) == Decimal("40.00")
    assert movs[0]["conta_id"] == conta_id

    r = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa",
        headers=h, json={"valor_pago": 60},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "paga"
    assert sum((Decimal(m["valor"]) for m in _movimentos(caixa["id"])), Decimal(0)) == Decimal("100.00")
