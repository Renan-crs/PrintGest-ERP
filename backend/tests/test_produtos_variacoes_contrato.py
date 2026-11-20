"""Produtos, serviços e variações — contrato e regras de negócio.

Cobre: pai deve ser produto, domínio de atributos, prefixo de 30 caracteres,
estoque por filha, idempotência após exclusão, soft-delete em cascata, RBAC
de preço e filtros de SKU/estoque.
"""

import uuid

from app.db import SessionLocal
from app.models.cadastros import Produto, ProdutoEstoque
from app.models.enums import NivelAcesso
from tests.conftest import auth
from tests.test_rbac import _criar_usuario, _login_usuario


def _u():
    return uuid.uuid4().hex[:8]


def _criar(client, token, tipo="produto", **extra):
    corpo = {"codigo": f"PV{_u().upper()}", "nome": f"Item {_u()}", "tipo": tipo}
    corpo.update(extra)
    r = client.post("/v1/produtos", headers=auth(client, token), json=corpo)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _gerar(client, token, pai_id, variacoes, prefixo=None):
    return client.post(
        "/v1/produtos/variacoes/gerar",
        headers=auth(client, token),
        json={
            "produto_pai_id": pai_id,
            "prefixo_sku": prefixo,
            "variacoes": variacoes,
        },
    )


def test_variacao_exige_produto_pai(client, admin_token):
    servico = _criar(client, admin_token, tipo="servico")
    r = _gerar(
        client, admin_token, servico["id"],
        [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
    )
    assert r.status_code == 400, r.text
    assert "servi" in r.json()["detail"].lower()


def test_variacao_sem_atributo_e_rejeitada(client, admin_token):
    pai = _criar(client, admin_token)
    r = _gerar(
        client, admin_token, pai["id"],
        [{"tamanho": "", "marca": "", "cor": ""}],
    )
    assert r.status_code == 422, r.text


def test_prefixo_sku_de_30_caracteres_e_aceito(client, admin_token):
    pai = _criar(client, admin_token)
    prefixo = "P" * 30
    r = _gerar(
        client, admin_token, pai["id"],
        [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
        prefixo=prefixo,
    )
    assert r.status_code in (200, 201), r.text  # antes: 422 (max_length=20)
    assert r.json()["data"][0]["sku"].startswith(prefixo[:8])


def test_filha_tem_estoque_proprio_e_pai_nao(client, admin_token):
    pai = _criar(client, admin_token)
    r = _gerar(
        client, admin_token, pai["id"],
        [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
    )
    assert r.status_code in (200, 201), r.text
    filha = r.json()["data"][0]
    assert filha["produto_pai_id"] == pai["id"]
    assert filha["tipo"] == "produto"
    assert filha["controla_estoque"] is True

    db = SessionLocal()
    try:
        estoque = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == filha["filial_id"],
                ProdutoEstoque.produto_id == filha["id"],
            )
            .first()
        )
        assert estoque is not None and estoque.saldo == 0
        pai_estoque = (
            db.query(ProdutoEstoque)
            .filter(ProdutoEstoque.produto_id == pai["id"])
            .first()
        )
        assert pai_estoque is None
    finally:
        db.close()

    busca = client.get(
        f"/v1/produtos/buscar-sku/{filha['sku']}", headers=auth(client, admin_token)
    )
    assert busca.status_code == 200, busca.text
    assert busca.json()["data"]["id"] == filha["id"]


def test_soft_delete_do_pai_desativa_filhas(client, admin_token):
    pai = _criar(client, admin_token)
    r = _gerar(
        client, admin_token, pai["id"],
        [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
    )
    filha_id = r.json()["data"][0]["id"]

    resp = client.delete(
        f"/v1/produtos/{pai['id']}", headers=auth(client, admin_token)
    )
    assert resp.status_code == 204, resp.text
    db = SessionLocal()
    try:
        assert db.get(Produto, pai["id"]).ativo is False
        assert db.get(Produto, filha_id).ativo is False
    finally:
        db.close()


def test_gerar_novamente_reativa_filha_excluida(client, admin_token):
    pai = _criar(client, admin_token)
    variacao = [{"tamanho": "M", "marca": "X", "cor": "Azul"}]
    primeira = _gerar(client, admin_token, pai["id"], variacao)
    filha_id = primeira.json()["data"][0]["id"]

    assert client.delete(
        f"/v1/produtos/{filha_id}", headers=auth(client, admin_token)
    ).status_code == 204
    # Idempotência reativa em vez de criar duplicata (SKU é único por filial).
    segunda = _gerar(client, admin_token, pai["id"], variacao)
    assert segunda.status_code in (200, 201), segunda.text
    db = SessionLocal()
    try:
        filhas = db.query(Produto).filter(Produto.produto_pai_id == pai["id"]).all()
        assert len(filhas) == 1
        assert filhas[0].id == filha_id
        assert filhas[0].ativo is True
    finally:
        db.close()


def test_operador_nao_altera_preco(client, admin_token):
    login, senha = _criar_usuario(client, admin_token, NivelAcesso.OPERADOR)
    operador = auth(client, _login_usuario(client, login, senha))
    produto = _criar(client, admin_token)

    r = client.put(
        f"/v1/produtos/{produto['id']}", headers=operador,
        json={"preco_venda": 999},
    )
    assert r.status_code == 403, r.text
    assert "gerência" in r.json()["detail"].lower()

    # Campos não sensíveis continuam permitidos ao operador.
    r = client.put(
        f"/v1/produtos/{produto['id']}", headers=operador,
        json={"nome": "Nome alterado"},
    )
    assert r.status_code == 200, r.text

    login_g, senha_g = _criar_usuario(client, admin_token, NivelAcesso.GERENTE)
    gerente = auth(client, _login_usuario(client, login_g, senha_g))
    assert client.put(
        f"/v1/produtos/{produto['id']}", headers=gerente,
        json={"preco_venda": 999},
    ).status_code == 200


def test_estoque_nao_movimenta_produto_inativo(client, admin_token):
    produto = _criar(client, admin_token)
    assert client.delete(
        f"/v1/produtos/{produto['id']}", headers=auth(client, admin_token)
    ).status_code == 204
    r = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, admin_token),
        json={"produto_id": produto["id"], "tipo": "entrada", "quantidade": 1},
    )
    assert r.status_code == 404, r.text


def test_campos_de_identidade_sao_imutaveis(client, admin_token):
    """SKU, uuid, pai e tipo não podem ser trocados via PUT."""
    pai = _criar(client, admin_token)
    r = _gerar(
        client, admin_token, pai["id"],
        [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
    )
    filha = r.json()["data"][0]
    h = auth(client, admin_token)

    # Mesmos valores: aceito (a UI reenvia o registro completo).
    assert client.put(
        f"/v1/produtos/{filha['id']}", headers=h,
        json={
            "sku": filha["sku"], "uuid": filha["uuid"],
            "produto_pai_id": pai["id"], "tipo": "produto",
        },
    ).status_code == 200

    for campo, valor in (
        ("sku", "OUTRO-SKU"),
        ("uuid", "00000000-0000-4000-8000-000000000000"),
        ("produto_pai_id", None),
        ("tipo", "servico"),
    ):
        resp = client.put(
            f"/v1/produtos/{filha['id']}", headers=h, json={campo: valor}
        )
        assert resp.status_code == 400, (campo, resp.text)
        assert campo in resp.json()["detail"]


def test_put_nao_altera_saldo_de_estoque(client, admin_token):
    """Saldo não é campo de cadastro — PUT não pode 'gravar' estoque."""
    produto = _criar(client, admin_token)
    h = auth(client, admin_token)
    assert client.post(
        "/v1/estoque/movimentar", headers=h,
        json={"produto_id": produto["id"], "tipo": "entrada", "quantidade": 7},
    ).status_code == 200

    assert client.put(
        f"/v1/produtos/{produto['id']}", headers=h,
        json={"nome": "Nome novo", "estoque_minimo": 3},
    ).status_code == 200

    db = SessionLocal()
    try:
        saldo = (
            db.query(ProdutoEstoque)
            .filter(ProdutoEstoque.produto_id == produto["id"])
            .one()
            .saldo
        )
        assert saldo == 7
    finally:
        db.close()


def test_schema_rejeita_variacao_sem_atributo():
    """Validação de domínio reside no schema, não só no serviço."""
    import pytest
    from pydantic import ValidationError

    from app.schemas.cadastros import VariacaoIn

    with pytest.raises(ValidationError):
        VariacaoIn(tamanho="", marca="", cor="")
    assert VariacaoIn(tamanho="M", marca="", cor="").tamanho == "M"
