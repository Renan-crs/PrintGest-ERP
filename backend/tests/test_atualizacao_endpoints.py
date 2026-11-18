"""Regressão: chamadas entre endpoints e atualização automática (PRD v3.3).

Garante que:
- criar/editar/excluir cadastro (categoria, produto, serviço, cliente) gera
  evento de sync na mesma transação e a listagem sempre lê do banco;
- venda lança movimento no caixa e evento de sync (o desktop recarrega o caixa
  após salvar/cancelar).
"""

import uuid

from app.db import SessionLocal
from app.models.financeiro import Caixa, MovimentoCaixa
from app.models.movimento import VendaBalcao
from app.models.plataforma import EventoSync
from tests.conftest import auth


def _u():
    return uuid.uuid4().hex[:8]


def test_cadastro_gera_evento_e_listagem_ve_alteracao(client, admin_token):
    h = auth(client, admin_token)

    cat = client.post(
        "/v1/categorias", headers=h, json={"nome": f"Cat {_u()}"}
    )
    assert cat.status_code == 200, cat.text

    produto = client.post(
        "/v1/produtos",
        headers=h,
        json={
            "codigo": f"P{_u().upper()}",
            "nome": "Produto atualização",
            "tipo": "produto",
            "unidade": "un",
            "preco_venda": 10.0,
            "categoria_id": cat.json()["data"]["id"],
        },
    )
    assert produto.status_code == 200, produto.text
    pid = produto.json()["data"]["id"]

    db = SessionLocal()
    try:
        ev = (
            db.query(EventoSync)
            .filter(EventoSync.entidade == "mestre:produto")
            .first()
        )
        assert ev is not None and ev.operacao == "CRS"
    finally:
        db.close()

    # Atualização gera evento UPD e a listagem (que lê do banco) reflete.
    alt = client.put(
        f"/v1/produtos/{pid}", headers=h, json={"nome": "Produto renomeado"}
    )
    assert alt.status_code == 200, alt.text
    lista = client.get(
        "/v1/produtos", headers=h, params={"q": "Produto renomeado"}
    ).json()["data"]
    assert any(p["id"] == pid for p in lista)

    db = SessionLocal()
    try:
        ups = (
            db.query(EventoSync)
            .filter(
                EventoSync.entidade == "mestre:produto",
                EventoSync.operacao == "UPD",
            )
            .count()
        )
        assert ups >= 1
    finally:
        db.close()

    # Exclusão (soft delete) também gera evento — a matriz precisa saber.
    exc = client.delete(f"/v1/produtos/{pid}", headers=h)
    assert exc.status_code == 204
    db = SessionLocal()
    try:
        dels = (
            db.query(EventoSync)
            .filter(
                EventoSync.entidade == "mestre:produto",
                EventoSync.operacao == "DEL",
            )
            .count()
        )
        assert dels >= 1
    finally:
        db.close()


def test_cliente_gera_evento_para_fila_de_conflitos(client, admin_token):
    h = auth(client, admin_token)
    resp = client.post(
        "/v1/clientes",
        headers=h,
        json={
            "nome_razao": f"Cliente {_u()}",
            "cpf_cnpj": uuid.uuid4().hex[:14],
            "tipo_pessoa": "pf",
        },
    )
    assert resp.status_code == 200, resp.text
    db = SessionLocal()
    try:
        ev = (
            db.query(EventoSync).filter(EventoSync.entidade == "cliente").first()
        )
        assert ev is not None and "cpf_cnpj" in ev.payload
    finally:
        db.close()


def test_venda_atualiza_caixa_e_evento(client, admin_token, caixa_admin):
    h = auth(client, admin_token)
    produto = client.post(
        "/v1/produtos",
        headers=h,
        json={
            "codigo": f"V{_u().upper()}",
            "nome": "Produto caixa",
            "tipo": "produto",
            "unidade": "un",
            "preco_venda": 20.0,
        },
    ).json()["data"]
    client.post(
        "/v1/estoque/movimentar",
        headers=h,
        json={"produto_id": produto["id"], "tipo": "entrada", "quantidade": 5},
    )
    venda = client.post(
        "/v1/vendas",
        headers=h,
        json={
            "forma_pagamento": "dinheiro",
            "valor_recebido": 20.0,
            "itens": [
                {
                    "produto_id": produto["id"],
                    "quantidade": 1,
                    "valor_unitario": 20.0,
                }
            ],
        },
    )
    assert venda.status_code == 200, venda.text

    db = SessionLocal()
    try:
        v = db.get(VendaBalcao, venda.json()["data"]["id"])
        caixa = db.get(Caixa, v.caixa_id)
        movimento = (
            db.query(MovimentoCaixa)
            .filter(MovimentoCaixa.venda_balcao_id == v.id)
            .first()
        )
        evento = (
            db.query(EventoSync)
            .filter(EventoSync.entidade == "venda_balcao")
            .first()
        )
        assert caixa is not None and movimento is not None and evento is not None
    finally:
        db.close()
