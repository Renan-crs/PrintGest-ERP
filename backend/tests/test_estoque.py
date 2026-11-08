"""Módulo Estoque (PRD v2.0 §1.3/§1.4) — consulta de saldos, movimentação manual, kardex e reposição."""

import uuid
from decimal import Decimal

from app.models.enums import NivelAcesso
from tests.conftest import auth


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_categoria(client, admin_token, nome=None):
    resp = client.post(
        "/v1/categorias",
        headers=auth(client, admin_token),
        json={"nome": nome or f"Categoria {_u()}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_produto(client, admin_token, **extra):
    payload = {
        "codigo": f"EST{uuid.uuid4().hex[:8].upper()}",
        "nome": "Papel Couché 90g",
        "tipo": "produto",
        "unidade": "resma",
        "preco_custo": 12.5,
        "preco_venda": 25.9,
        "estoque_minimo": 5,
    }
    payload.update(extra)
    resp = client.post("/v1/produtos", headers=auth(client, admin_token), json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _movimentar(client, admin_token, produto_id, tipo, quantidade, **extra):
    payload = {"produto_id": produto_id, "tipo": tipo, "quantidade": quantidade}
    payload.update(extra)
    return client.post(
        "/v1/estoque/movimentar", headers=auth(client, admin_token), json=payload
    )


def test_consulta_estoque_saldo_zero(client, admin_token):
    produto = _criar_produto(client, admin_token)
    resp = client.get("/v1/estoque", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    linha = next(i for i in resp.json()["data"] if i["produto_id"] == produto["id"])
    assert Decimal(linha["saldo"]) == Decimal(0)
    assert linha["status"] == "critico"  # 0 < mínimo 5
    assert Decimal(linha["valor_estoque"]) == Decimal("0.00")
    assert "categoria_nome" in linha


def test_resumo_estoque(client, admin_token):
    _criar_produto(client, admin_token)
    resp = client.get("/v1/estoque/resumo", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert dados["total_itens"] >= 1
    assert dados["abaixo_minimo"] >= 1
    assert Decimal(dados["valor_total"]) >= Decimal("0.00")


def test_movimentacao_entrada_atualiza_saldo_e_kardex(client, admin_token):
    produto = _criar_produto(client, admin_token)
    resp = _movimentar(
        client, admin_token, produto["id"], "entrada", 10, motivo="Entrada NF-e"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert Decimal(data["saldo"]) == Decimal(10)
    assert data["movimento"]["tipo"] == "entrada"
    assert data["movimento"]["origem"] == "ajuste_manual"
    assert Decimal(data["movimento"]["quantidade"]) == Decimal(10)
    assert Decimal(data["movimento"]["saldo_anterior"]) == Decimal(0)
    assert Decimal(data["movimento"]["saldo_posterior"]) == Decimal(10)

    kardex = client.get(
        f"/v1/estoque/{produto['id']}/kardex", headers=auth(client, admin_token)
    )
    assert kardex.status_code == 200, kardex.text
    assert kardex.json()["meta"]["total"] == 1
    mov = kardex.json()["data"][0]
    assert mov["tipo"] == "entrada"


def test_movimentacao_saida_e_estoque_insuficiente(client, admin_token):
    produto = _criar_produto(client, admin_token)
    _movimentar(client, admin_token, produto["id"], "entrada", 10)
    resp = _movimentar(client, admin_token, produto["id"], "saida", 4)
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["data"]["saldo"]) == Decimal(6)

    resp = _movimentar(client, admin_token, produto["id"], "saida", 99)
    assert resp.status_code == 409
    assert "insuficiente" in resp.json()["detail"].lower()


def test_movimentacao_ajuste_iguala_saldo(client, admin_token):
    produto = _criar_produto(client, admin_token)
    _movimentar(client, admin_token, produto["id"], "entrada", 25)
    resp = _movimentar(
        client, admin_token, produto["id"], "ajuste", 2, motivo="Balanço Gaveta 04"
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert Decimal(data["saldo"]) == Decimal(2)
    assert Decimal(data["movimento"]["quantidade"]) == Decimal(-23)
    assert Decimal(data["movimento"]["saldo_posterior"]) == Decimal(2)


def test_movimentacao_servico_nao_tem_estoque(client, admin_token):
    servico = _criar_produto(
        client,
        admin_token,
        tipo="servico",
        controla_estoque=False,
        codigo=f"SERV_{_u()}",
        preco_custo=0,
    )
    resp = _movimentar(client, admin_token, servico["id"], "entrada", 5)
    assert resp.status_code == 400
    assert "estoque" in resp.json()["detail"].lower()


def test_filtro_abaixo_do_minimo(client, admin_token):
    abaixo = _criar_produto(client, admin_token)  # saldo 0, mínimo 5
    _criar_produto(client, admin_token, estoque_minimo=0)  # nunca abaixo
    cliente = _criar_produto(client, admin_token)
    _movimentar(
        client,
        admin_token,
        cliente["id"],
        "entrada",
        50,
    )

    resp = client.get(
        "/v1/estoque", params={"abaixo_minimo": True}, headers=auth(client, admin_token)
    )
    assert resp.status_code == 200, resp.text
    ids = [i["produto_id"] for i in resp.json()["data"]]
    assert abaixo["id"] in ids
    assert cliente["id"] not in ids


def test_reposicao_lista_criticos_e_sugere_lote(client, admin_token):
    produto = _criar_produto(client, admin_token)
    _movimentar(client, admin_token, produto["id"], "entrada", 2)  # mínimo 5
    resp = client.get("/v1/estoque/reposicao", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    linha = next(i for i in resp.json()["data"] if i["produto_id"] == produto["id"])
    assert Decimal(linha["saldo"]) == Decimal(2)
    assert Decimal(linha["estoque_minimo"]) == Decimal(5)
    assert linha["status"] == "critico"
    # sem consumo nos últimos 30d → giro 0, sem autonomia, sugere só até o mínimo
    assert Decimal(linha["giro_diario"]) == Decimal(0)
    assert linha["autonomia_dias"] is None
    assert Decimal(linha["sugestao"]) >= Decimal(3)


def test_reposicao_apos_consumo_calcula_giro(client, admin_token):
    produto = _criar_produto(client, admin_token, estoque_minimo=200)
    _movimentar(client, admin_token, produto["id"], "entrada", 100)
    for _ in range(5):
        _movimentar(client, admin_token, produto["id"], "saida", 3)

    resp = client.get("/v1/estoque/reposicao", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    linha = next(i for i in resp.json()["data"] if i["produto_id"] == produto["id"])
    # 15 unidades consumidas em 30 dias
    assert Decimal(linha["giro_diario"]) == Decimal("0.5")
    assert Decimal(linha["autonomia_dias"]) == Decimal(170)
    assert Decimal(linha["sugestao"]) > Decimal(0)


def test_estoque_requer_operador(client, admin_token):
    login, senha = f"cx{uuid.uuid4().hex[:8]}", "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": "Caixa Estoque",
            "login": login,
            "senha": senha,
            "nivel_acesso": NivelAcesso.CAIXA.value,
        },
    )
    assert resp.status_code == 200, resp.text
    token = client.post("/v1/auth/login", json={"login": login, "senha": senha}).json()[
        "data"
    ]["token"]

    resp = client.get("/v1/estoque", headers=auth(client, token))
    assert resp.status_code == 403
    resp = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, token),
        json={"produto_id": 1, "tipo": "entrada", "quantidade": 1},
    )
    assert resp.status_code == 403
