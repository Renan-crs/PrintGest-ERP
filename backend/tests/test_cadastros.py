"""Cadastros (PRD v2.0 §1.3 / telas_e_fluxos §1.2) — CRUD e validações."""

import uuid
from decimal import Decimal

from tests.conftest import auth


def _u():
    return uuid.uuid4().hex[:8]


# --- Clientes -----------------------------------------------------------------


def test_criar_cliente_pf(client, admin_token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={
            "nome_razao": "Maria da Silva",
            "tipo_pessoa": "pf",
            "cpf_cnpj": f"{_u()[:11]}",
            "email": "maria@teste.com",
            "telefone": "1122223333",
            "data_nascimento": "1990-05-10",
            "cidade": "São Paulo",
            "uf": "SP",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["nome_razao"] == "Maria da Silva"
    assert data["filial_id"] == 1
    assert data["ativo"] is True


def test_cliente_busca_rapida(client, admin_token):
    nome = f"Cliente Busca {_u()}"
    created = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": nome, "tipo_pessoa": "pf"},
    )
    assert created.status_code == 200, created.text
    resp = client.get("/v1/clientes", params={"q": "Busca", "limit": 10},
                      headers=auth(client, admin_token))
    assert resp.status_code == 200
    nomes = [c["nome_razao"] for c in resp.json()["data"]]
    assert nome in nomes


def test_cliente_detalhe_404(client, admin_token):
    resp = client.get("/v1/clientes/999999", headers=auth(client, admin_token))
    assert resp.status_code == 404
    assert resp.json()["detail"]


def test_cliente_duplicado_cpf_cnpj_409(client, admin_token):
    cpf = _u()[:11]
    client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Primeiro", "cpf_cnpj": cpf},
    )
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Duplicado", "cpf_cnpj": cpf},
    )
    assert resp.status_code == 409
    assert "duplicado" in resp.json()["detail"].lower()


def test_cliente_update_parcial_soft_delete(client, admin_token):
    created = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Editar e Remover", "tipo_pessoa": "pf"},
    )
    cli_id = created.json()["data"]["id"]

    resp = client.put(
        f"/v1/clientes/{cli_id}",
        headers=auth(client, admin_token),
        json={"telefone": "11999990000"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["telefone"] == "11999990000"

    resp = client.delete(f"/v1/clientes/{cli_id}", headers=auth(client, admin_token))
    assert resp.status_code == 204

    resp = client.get(f"/v1/clientes/{cli_id}", headers=auth(client, admin_token))
    assert resp.status_code == 404

    resp = client.get(f"/v1/clientes?q=Editar+e+Remover", headers=auth(client, admin_token))
    assert all(c["nome_razao"] != "Editar e Remover" for c in resp.json()["data"])


def test_clientes_obrigatorio_nome(client, admin_token):
    resp = client.post(
        "/v1/clientes", headers=auth(client, admin_token), json={"tipo_pessoa": "pf"}
    )
    assert resp.status_code == 422


def test_clientes_paginacao_meta(client, admin_token):
    for i in range(3):
        client.post(
            "/v1/clientes",
            headers=auth(client, admin_token),
            json={"nome_razao": f"Pagina {_u()}"},
        )
    resp = client.get("/v1/clientes", params={"limit": 1, "offset": 0},
                      headers=auth(client, admin_token))
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["limit"] == 1
    assert meta["offset"] == 0
    assert meta["total"] >= 3
    assert len(resp.json()["data"]) == 1

    resp = client.get("/v1/clientes", params={"limit": 1000},
                      headers=auth(client, admin_token))
    assert resp.json()["meta"]["limit"] == 200


# --- Fornecedores -------------------------------------------------------------


def test_fornecedor_crud(client, admin_token):
    created = client.post(
        "/v1/fornecedores",
        headers=auth(client, admin_token),
        json={
            "nome_razao": "Papelaria Central Ltda",
            "tipo_pessoa": "pj",
            "cpf_cnpj": f"{_u()[:11]}",
            "contato_nome": "João Comprador",
        },
    )
    assert created.status_code == 200, created.text
    forn_id = created.json()["data"]["id"]
    assert created.json()["data"]["filial_id"] == 1

    resp = client.get("/v1/fornecedores", params={"q": "Central"},
                      headers=auth(client, admin_token))
    assert any(f["nome_razao"] == "Papelaria Central Ltda" for f in resp.json()["data"])

    resp = client.put(f"/v1/fornecedores/{forn_id}",
                      headers=auth(client, admin_token),
                      json={"telefone": "1133334444"})
    assert resp.status_code == 200
    assert resp.json()["data"]["telefone"] == "1133334444"

    resp = client.delete(f"/v1/fornecedores/{forn_id}", headers=auth(client, admin_token))
    assert resp.status_code == 204


# --- Funcionários / Vendedores / Atendentes ------------------------------------


def test_funcionario_crud(client, admin_token):
    created = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={
            "nome": "Funcionario Teste",
            "cpf": _u()[:11],
            "cargo": "Atendente",
            "e_atendente": True,
            "e_vendedor": True,
            "comissao_pct": 3.5,
        },
    )
    assert created.status_code == 200, created.text
    func_id = created.json()["data"]["id"]
    assert created.json()["data"]["filial_id"] == 1
    assert created.json()["data"]["e_atendente"] is True
    assert created.json()["data"]["e_vendedor"] is True
    assert Decimal(created.json()["data"]["comissao_pct"]) == Decimal("3.500")

    resp = client.get("/v1/funcionarios", params={"q": "Atendente"},
                      headers=auth(client, admin_token))
    assert any(f["nome"] == "Funcionario Teste" for f in resp.json()["data"])

    resp = client.put(f"/v1/funcionarios/{func_id}",
                      headers=auth(client, admin_token),
                      json={"cargo": "Gerente de Produção"})
    assert resp.status_code == 200
    assert resp.json()["data"]["cargo"] == "Gerente de Produção"


def test_funcionario_duplicado_cpf_409(client, admin_token):
    cpf = _u()[:11]
    client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Um", "cpf": cpf},
    )
    resp = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Dois", "cpf": cpf},
    )
    assert resp.status_code == 409


# --- Categorias de Produto ------------------------------------------------------


def test_categoria_crud(client, admin_token):
    created = client.post(
        "/v1/categorias",
        headers=auth(client, admin_token),
        json={"nome": f"Categoria {_u()}", "description": "Papéis e cartolinas"},
    )
    assert created.status_code == 200, created.text
    cat_id = created.json()["data"]["id"]

    resp = client.get("/v1/categorias", params={"q": "Categoria"},
                      headers=auth(client, admin_token))
    assert any(c["id"] == cat_id for c in resp.json()["data"])

    resp = client.put(f"/v1/categorias/{cat_id}",
                      headers=auth(client, admin_token),
                      json={"description": "Papéis especiais"})
    assert resp.status_code == 200
    assert resp.json()["data"]["description"] == "Papéis especiais"

    resp = client.delete(f"/v1/categorias/{cat_id}", headers=auth(client, admin_token))
    assert resp.status_code == 204


def test_categoria_duplicado_nome_409(client, admin_token):
    nome = f"Categoria Duplicada {_u()}"
    client.post("/v1/categorias", headers=auth(client, admin_token), json={"nome": nome})
    resp = client.post("/v1/categorias", headers=auth(client, admin_token), json={"nome": nome})
    assert resp.status_code == 409


# --- Produtos / Serviços ----------------------------------------------------------


def test_produto_crud(client, admin_token):
    cat = client.post(
        "/v1/categorias", headers=auth(client, admin_token), json={"nome": f"ProdCat {_u()}"}
    ).json()["data"]
    codigo = f"P{uuid.uuid4().hex[:8].upper()}"

    created = client.post(
        "/v1/produtos",
        headers=auth(client, admin_token),
        json={
            "codigo": codigo,
            "nome": "Papel A4 75g",
            "tipo": "produto",
            "unidade": "resma",
            "preco_custo": 12.5,
            "preco_venda": 25.9,
            "estoque_minimo": 10,
            "controla_estoque": True,
            "categoria_id": cat["id"],
            "dimensoes": "21x29,7",
        },
    )
    assert created.status_code == 200, created.text
    prod = created.json()["data"]
    assert prod["filial_id"] == 1
    assert Decimal(prod["preco_custo"]) == Decimal("12.50")
    assert Decimal(prod["preco_venda"]) == Decimal("25.90")
    assert prod["tipo"] == "produto"

    resp = client.get("/v1/produtos", params={"q": "A4"},
                      headers=auth(client, admin_token))
    assert any(p["codigo"] == codigo for p in resp.json()["data"])

    resp = client.put(f"/v1/produtos/{prod['id']}",
                      headers=auth(client, admin_token),
                      json={"preco_venda": 29.9})
    assert resp.status_code == 200
    assert Decimal(resp.json()["data"]["preco_venda"]) == Decimal("29.90")


def test_produto_servico_sem_estoque(client, admin_token):
    resp = client.post(
        "/v1/produtos",
        headers=auth(client, admin_token),
        json={
            "codigo": f"S{uuid.uuid4().hex[:8].upper()}",
            "nome": "Serviço de Plotagem",
            "tipo": "servico",
            "controla_estoque": False,
            "preco_venda": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["tipo"] == "servico"


def test_produto_duplicado_codigo_409(client, admin_token):
    codigo = f"DUPL{uuid.uuid4().hex[:6].upper()}"
    client.post("/v1/produtos", headers=auth(client, admin_token),
                json={"codigo": codigo, "nome": "Produto duplicado"})
    resp = client.post("/v1/produtos", headers=auth(client, admin_token),
                       json={"codigo": codigo, "nome": "Produto duplicado 2"})
    assert resp.status_code == 409


def test_produto_validacao_campos(client, admin_token):
    resp = client.post("/v1/produtos", headers=auth(client, admin_token), json={})
    assert resp.status_code == 422

    resp = client.post(
        "/v1/produtos",
        headers=auth(client, admin_token),
        json={"codigo": "NEG1", "nome": "Negativo", "preco_venda": -1},
    )
    assert resp.status_code == 422