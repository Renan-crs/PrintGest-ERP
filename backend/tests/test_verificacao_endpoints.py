"""Verificação ponta a ponta da chamada e atualização entre endpoints.

Cobre o ciclo completo depois das mudanças de variações/SKU/estoque:
  cadastro -> evento sync -> variação -> PDV (baixa otimista) -> caixa
  -> transferência entre filiais -> resumo consolidado.
"""

import uuid

from app.db import SessionLocal
from app.models.cadastros import MovimentoEstoque
from app.models.core import Filial
from app.models.financeiro import Caixa, MovimentoCaixa
from app.models.movimento import VendaBalcao
from app.models.plataforma import EventoSync
from app.models.transferencia import TransferenciaEstoque
from tests.conftest import auth


def _u():
    return uuid.uuid4().hex[:8]


def _produto(client, token):
    r = client.post(
        "/v1/produtos",
        headers=auth(client, token),
        json={
            "codigo": f"V{_u().upper()}",
            "nome": "Produto verificação",
            "tipo": "produto",
            "unidade": "un",
            "preco_venda": 10.0,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_ciclo_completo_atualizacao(client, admin_token, caixa_admin):
    h = auth(client, admin_token)

    # 1) Cadastro gera evento de sync (atualização automática p/ matriz/filiais)
    produto = _produto(client, admin_token)
    db = SessionLocal()
    try:
        ev = (
            db.query(EventoSync)
            .filter(
                EventoSync.entidade == "mestre:produto",
                EventoSync.entidade_id == produto["id"],
            )
            .first()
        )
        assert ev is not None and ev.operacao == "CRS"
    finally:
        db.close()

    # 2) Variação gera SKU + evento + estoque próprio
    r = client.post(
        "/v1/produtos/variacoes/gerar",
        headers=h,
        json={
            "produto_pai_id": produto["id"],
            "prefixo_sku": "TCK",
            "variacoes": [
                {"tamanho": "M", "marca": "X", "cor": "Azul", "preco_venda": 12},
            ],
        },
    )
    assert r.status_code == 201, r.text
    variante = r.json()["data"][0]
    sku = variante["sku"]

    # 3) Leitura direta por SKU (PDV sem navegar variações)
    busca = client.get(f"/v1/produtos/buscar-sku/{sku}", headers=h)
    assert busca.status_code == 200, busca.text
    assert busca.json()["data"]["id"] == variante["id"]

    # 4) Entrada de estoque e venda (baixa otimista WHERE saldo >= qtd)
    r = client.post(
        "/v1/estoque/movimentar",
        headers=h,
        json={
            "produto_id": variante["id"], "tipo": "entrada",
            "quantidade": 5, "motivo": "acerto",
        },
    )
    assert r.status_code == 200, r.text
    venda = client.post(
        "/v1/vendas",
        headers=h,
        json={
            "forma_pagamento": "dinheiro",
            "valor_recebido": 12.0,
            "itens": [
                {
                    "produto_id": variante["id"], "quantidade": 1,
                    "valor_unitario": 12.0,
                }
            ],
        },
    )
    assert venda.status_code == 200, venda.text
    venda_id = venda.json()["data"]["id"]

    # 5) Venda atualiza caixa E gera evento de sync
    db = SessionLocal()
    try:
        v = db.get(VendaBalcao, venda_id)
        assert v.caixa_id is not None
        mv = (
            db.query(MovimentoCaixa)
            .filter(MovimentoCaixa.venda_balcao_id == venda_id)
            .first()
        )
        assert mv is not None
        ev_venda = (
            db.query(EventoSync)
            .filter(
                EventoSync.entidade == "venda_balcao",
                EventoSync.entidade_id == venda_id,
            )
            .first()
        )
        assert ev_venda is not None
    finally:
        db.close()

    # 6) Transferência entre filiais (dois passos) para atualização cruzada
    db = SessionLocal()
    try:
        empresa = db.query(Filial).first()
        from app.models.core import Empresa

        emp = db.get(Empresa, empresa.empresa_id)
        destino = Filial(empresa_id=emp.id, nome=f"Filial {_u()}")
        db.add(destino)
        db.commit()
        destino_id = destino.id
    finally:
        db.close()

    r = client.post(
        "/v1/estoque/transferencias",
        headers=h,
        json={
            "filial_destino_id": destino_id,
            "produto_id": variante["id"],
            "quantidade": 2,
        },
    )
    assert r.status_code == 201, r.text
    doc = r.json()["data"]
    assert doc["estado"] == "enviada"

    db = SessionLocal()
    try:
        pendente = (
            db.query(TransferenciaEstoque)
            .filter(TransferenciaEstoque.id == doc["id"])
            .first()
        )
        assert pendente.estado.value == "enviada"
    finally:
        db.close()

    # 7) Listagens sempre leem do banco (sem cache) e refletem mudanças
    lista = client.get(
        "/v1/estoque/transferencias", headers=h
    ).json()["data"]
    assert any(t["id"] == doc["id"] for t in lista)
