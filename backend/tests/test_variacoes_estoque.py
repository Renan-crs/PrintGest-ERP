"""Variações/SKU, baixa otimista e transferência entre filiais (PRD v3.2)."""

import uuid

import pytest
from app.db import SessionLocal
from app.models.cadastros import MovimentoEstoque, ProdutoEstoque
from app.models.transferencia import TransferenciaEstoque
from tests.conftest import auth


def _u():
    return uuid.uuid4().hex[:8]


def _produto(client, token, nome=None, preco=10.0):
    r = client.post(
        "/v1/produtos",
        headers=auth(client, token),
        json={
            "codigo": f"P{_u().upper()}",
            "nome": nome or f"Produto {_u()}",
            "tipo": "produto",
            "unidade": "un",
            "preco_venda": preco,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _entrada(client, token, produto_id, qtd):
    r = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, token),
        json={"produto_id": produto_id, "tipo": "entrada", "quantidade": qtd, "motivo": "acerto"},
    )
    assert r.status_code == 200, r.text


def test_gerar_variacoes_com_sku_e_uuid(client, admin_token):
    h = auth(client, admin_token)
    pai = _produto(client, admin_token, nome="Carimbo")
    r = client.post(
        "/v1/produtos/variacoes/gerar",
        headers=h,
        json={
            "produto_pai_id": pai["id"],
            "prefixo_sku": "CAR",
            "variacoes": [
                {"tamanho": "M", "marca": "MarcaX", "cor": "Azul", "preco_venda": 15},
                {"tamanho": "G", "marca": "MarcaX", "cor": "Vermelho"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    filhas = r.json()["data"]
    assert len(filhas) == 2

    skus = {f["sku"] for f in filhas}
    assert skus == {"CAR-M-MARCAX-AZUL", "CAR-G-MARCAX-VERMELHO"}
    for filha in filhas:
        assert filha["uuid"] and filha["produto_pai_id"] == pai["id"]
        assert filha["preco_venda"] is not None

    # Busca direta por SKU (sem navegar variações no PDV)
    busca = client.get(
        "/v1/produtos/buscar-sku/CAR-M-MARCAX-AZUL", headers=h
    )
    assert busca.status_code == 200, busca.text
    assert busca.json()["data"]["sku"] == "CAR-M-MARCAX-AZUL"

    # Idempotente: repetir não duplica
    r2 = client.post(
        "/v1/produtos/variacoes/gerar",
        headers=h,
        json={
            "produto_pai_id": pai["id"],
            "prefixo_sku": "CAR",
            "variacoes": [
                {"tamanho": "M", "marca": "MarcaX", "cor": "Azul"},
            ],
        },
    )
    assert r2.json()["data"] == []


def test_ajuste_exige_motivo(client, admin_token):
    h = auth(client, admin_token)
    produto = _produto(client, admin_token)
    r = client.post(
        "/v1/estoque/movimentar",
        headers=h,
        json={"produto_id": produto["id"], "tipo": "ajuste", "quantidade": 5},
    )
    assert r.status_code == 422  # motivo obrigatório

    r = client.post(
        "/v1/estoque/movimentar",
        headers=h,
        json={
            "produto_id": produto["id"], "tipo": "ajuste", "quantidade": 5,
            "motivo": "contagem",  # domínio fechado sugerido na UI
        },
    )
    assert r.status_code == 200, r.text


def test_baixa_otimista_update_where_saldo(client, admin_token, caixa_admin):
    h = auth(client, admin_token)
    produto = _produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 1)
    cliente = client.post(
        "/v1/clientes",
        headers=h,
        json={"nome_razao": f"Cliente {_u()}", "tipo_pessoa": "pf"},
    ).json()["data"]

    def _vender():
        return client.post(
            "/v1/vendas",
            headers=h,
            json={
                "cliente_id": cliente["id"],
                "forma_pagamento": "pix",
                "itens": [
                    {
                        "produto_id": produto["id"], "quantidade": 1,
                        "valor_unitario": 10.0,
                    }
                ],
            },
        )

    r1 = _vender()
    assert r1.status_code == 200, r1.text
    r2 = _vender()  # saldo esgotado
    assert r2.status_code == 409
    assert "estoque" in r2.json()["detail"].lower()

    db = SessionLocal()
    try:
        saldo = (
            db.query(ProdutoEstoque)
            .filter(ProdutoEstoque.produto_id == produto["id"])
            .first()
            .saldo
        )
        assert saldo == 0
    finally:
        db.close()


def test_transferencia_dois_passos(client, admin_token):
    h = auth(client, admin_token)
    db = SessionLocal()
    try:
        empresas = db.execute(__import__("sqlalchemy").text(
            "SELECT id FROM empresa ORDER BY id"
        )).fetchall()
        filial_origem = db.execute(__import__("sqlalchemy").text(
            "SELECT id FROM filial ORDER BY id LIMIT 1"
        )).scalar()
        # Cria uma segunda filial para o destino
        from app.models.core import Empresa, Filial

        empresa = db.query(Empresa).first()
        destino = Filial(empresa_id=empresa.id, nome=f"Filial {_u()}")
        db.add(destino)
        db.commit()
        fid = destino.id
    finally:
        db.close()

    produto = _produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    r = client.post(
        "/v1/estoque/transferencias",
        headers=h,
        json={
            "filial_destino_id": fid,
            "produto_id": produto["id"],
            "quantidade": 3,
            "observacoes": "Teste transferência",
        },
    )
    assert r.status_code == 201, r.text
    doc = r.json()["data"]
    assert doc["estado"] == "enviada"

    db = SessionLocal()
    try:
        saldo_origem = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == filial_origem,
                ProdutoEstoque.produto_id == produto["id"],
            )
            .first()
            .saldo
        )
        saldo_destino = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == fid,
                ProdutoEstoque.produto_id == produto["id"],
            )
            .first()
        )
        assert saldo_origem == 7  # saiu na origem
        assert saldo_destino is None  # destino ainda NÃO recebeu
    finally:
        db.close()

    # Confirmação na filial de destino (admin da filial 1 é de outra filial →
    # usamos a rota diretamente com o token; o escopo é validado no serviço).
    r2 = client.post(
        f"/v1/estoque/transferencias/{doc['id']}/receber", headers=h
    )
    # A filial do usuário (1) não é a de destino → 403 esperado.
    assert r2.status_code == 403

    # Confirmação como admin da filial de destino: cria usuário lá.
    from app.models.core import Usuario

    db = SessionLocal()
    try:
        admin_destino = client.post(
            "/v1/usuarios",
            headers=h,
            json={
                "nome": "Admin destino",
                "login": f"dest{_u()}",
                "senha": "senha123",
                "nivel_acesso": "admin",
            },
        )
        # O usuário é criado na filial do admin (1); para testar o recebimento
        # precisamos de um token com filial_destino — feito via sessão direta.
        uid = admin_destino.json()["data"]["id"]
        u = db.get(Usuario, uid)
        u.filial_id = fid
        db.commit()
        login_dest = u.login
    finally:
        db.close()
    token_dest = client.post(
        "/v1/auth/login", json={"login": login_dest, "senha": "senha123"}
    ).json()["data"]["token"]

    r3 = client.post(
        f"/v1/estoque/transferencias/{doc['id']}/receber",
        headers=auth(client, token_dest),
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["data"]["estado"] == "recebida"

    db = SessionLocal()
    try:
        saldo_destino = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == fid,
                ProdutoEstoque.produto_id == produto["id"],
            )
            .first()
            .saldo
        )
        assert saldo_destino == 3  # destino recebeu somente após confirmação
    finally:
        db.close()
