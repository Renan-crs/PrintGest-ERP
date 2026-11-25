"""Fase V1 — regras de preço persistidas, precedência, vigência e snapshot."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from tests.conftest import auth


def _produto(client, token: str) -> dict:
    resp = client.post(
        "/v1/produtos",
        headers=auth(client, token),
        json={
            "codigo": f"RP{uuid.uuid4().hex[:10].upper()}",
            "nome": "Impressão sulfite A4",
            "tipo": "servico",
            "unidade": "un",
            "controla_estoque": False,
            "preco_venda": "20.00",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _tabela_padrao(client, token: str) -> dict:
    """Reutiliza a tabela padrão da suíte (só pode existir uma por filial)."""
    existentes = client.get(
        "/v1/precificacao/tabelas", headers=auth(client, token)
    ).json()["data"]
    for tabela in existentes:
        if tabela["padrao"]:
            return tabela
    resp = client.post(
        "/v1/precificacao/tabelas",
        headers=auth(client, token),
        json={"nome": "Tabela padrão", "padrao": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _regra(
    client,
    token: str,
    *,
    tabela_id: int,
    produto_id: int,
    preco_base: str = "1.00",
    **extra,
) -> dict:
    payload = {
        "tabela_preco_id": tabela_id,
        "produto_id": produto_id,
        "preco_base": preco_base,
    }
    payload.update(extra)
    resp = client.post(
        "/v1/precificacao/regras", headers=auth(client, token), json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _faixas() -> list[dict]:
    return [
        {"qtd_min": 1, "qtd_max": 49, "preco_unitario": "1.00"},
        {"qtd_min": 50, "qtd_max": 199, "preco_unitario": "0.80"},
        {"qtd_min": 200, "qtd_max": None, "preco_unitario": "0.60"},
    ]


def _vender(client, token, produto_id, **extra):
    payload = {
        "forma_pagamento": "dinheiro",
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": 120,
                # Cliente envia preço inflado: a regra do banco é que vale.
                "valor_unitario": "999.00",
            }
        ],
    }
    payload.update(extra)
    return client.post("/v1/vendas", headers=auth(client, token), json=payload)


# ------------------------------------------------------------------- venda


def test_venda_usa_regra_persistida_e_grava_snapshot(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    regra = _regra(
        client,
        admin_token,
        tabela_id=tabela["id"],
        produto_id=produto["id"],
        faixas=_faixas(),
    )

    resp = _vender(client, admin_token, produto["id"])
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    assert item["valor_unitario"] == "0.80"
    assert item["valor_total"] == "96.00"
    assert item["explicacao"]  # transiente da resposta
    snapshot = item["regra_aplicada"]
    assert snapshot["origem"] == "tabela_padrao"
    assert snapshot["regra_id"] == regra["id"]
    assert snapshot["explicacao"] == item["explicacao"]

    # RF-VR-21: o snapshot sobrevive ao GET e congela o cálculo.
    venda_id = resp.json()["data"]["id"]
    consultado = client.get(
        f"/v1/vendas/{venda_id}", headers=auth(client, admin_token)
    )
    assert consultado.status_code == 200, consultado.text
    item_gravado = consultado.json()["data"]["itens"][0]
    assert item_gravado["regra_aplicada"]["regra_id"] == regra["id"]
    assert item_gravado["valor_total"] == "96.00"


def test_sem_regra_persistida_mantem_preco_do_cliente(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    _tabela_padrao(client, admin_token)  # tabela sem regra para este produto

    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {
                    "produto_id": produto["id"],
                    "quantidade": 3,
                    "valor_unitario": "20.00",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    assert item["valor_unitario"] == "20.00"
    assert item["regra_aplicada"] is None


def test_regra_encerrada_deixa_de_valer(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    regra = _regra(
        client,
        admin_token,
        tabela_id=tabela["id"],
        produto_id=produto["id"],
        preco_base="5.00",
    )
    resp = client.post(
        f"/v1/precificacao/regras/{regra['id']}/encerrar",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text

    venda = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {
                    "produto_id": produto["id"],
                    "quantidade": 2,
                    "valor_unitario": "20.00",
                }
            ],
        },
    )
    assert venda.status_code == 200, venda.text
    assert venda.json()["data"]["itens"][0]["valor_unitario"] == "20.00"


def test_sucessora_nao_altera_regra_ja_usada(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    antiga = _regra(
        client,
        admin_token,
        tabela_id=tabela["id"],
        produto_id=produto["id"],
        preco_base="5.00",
    )
    primeira = _vender(client, admin_token, produto["id"])
    assert primeira.status_code == 200, primeira.text

    sucessora = client.post(
        f"/v1/precificacao/regras/{antiga['id']}/suceder",
        headers=auth(client, admin_token),
        json={
            "tabela_preco_id": tabela["id"],
            "produto_id": produto["id"],
            "preco_base": "9.00",
        },
    )
    assert sucessora.status_code == 201, sucessora.text
    assert sucessora.json()["data"]["id"] != antiga["id"]

    segunda = _vender(client, admin_token, produto["id"])
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["data"]["itens"][0]["valor_unitario"] == "9.00"

    # O documento antigo continua congelado na regra original.
    antiga_gravada = client.get(
        f"/v1/vendas/{primeira.json()['data']['id']}",
        headers=auth(client, admin_token),
    ).json()["data"]["itens"][0]
    assert antiga_gravada["regra_aplicada"]["regra_id"] == antiga["id"]
    assert antiga_gravada["valor_total"] == "600.00"  # 5,00 × 120, congelado
    assert antiga_gravada["valor_unitario"] == "5.00"


def test_regra_com_vigencia_futura_nao_vale(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    futuro = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    _regra(
        client,
        admin_token,
        tabela_id=tabela["id"],
        produto_id=produto["id"],
        preco_base="7.00",
        vigencia_inicio=futuro,
    )
    resp = _vender(client, admin_token, produto["id"])
    assert resp.status_code == 200, resp.text
    # Sem regra vigente, volta o comportamento legado (valor enviado).
    assert resp.json()["data"]["itens"][0]["valor_unitario"] == "999.00"


def test_os_usa_regra_persistida_e_grava_snapshot(client, admin_token):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    regra = _regra(
        client,
        admin_token,
        tabela_id=tabela["id"],
        produto_id=produto["id"],
        preco_base="2.50",
    )
    cliente = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": f"Cliente OS V1 {uuid.uuid4().hex[:6]}", "tipo_pessoa": "pf"},
    ).json()["data"]
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "produto_id": produto["id"],
                    "quantidade": 4,
                    "valor_unitario": "999.00",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    assert item["valor_unitario"] == "2.50"
    assert item["valor_total"] == "10.00"
    assert item["regra_aplicada"]["regra_id"] == regra["id"]

    os_id = resp.json()["data"]["id"]
    consultado = client.get(f"/v1/os/{os_id}", headers=auth(client, admin_token))
    assert consultado.status_code == 200, consultado.text
    gravado = consultado.json()["data"]["itens"][0]
    assert gravado["regra_aplicada"]["regra_id"] == regra["id"]
    assert gravado["explicacao"] == []  # transiente, não sobrevive ao GET
    assert gravado["valor_total"] == "10.00"


# ------------------------------------------------------------ API e RBAC


def test_precedencia_da_tabela_do_cliente(client, admin_token, caixa_admin):
    produto = _produto(client, admin_token)
    cliente = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": f"Cliente V1 {uuid.uuid4().hex[:6]}", "tipo_pessoa": "pf"},
    ).json()["data"]
    padrao = _tabela_padrao(client, admin_token)
    _regra(
        client,
        admin_token,
        tabela_id=padrao["id"],
        produto_id=produto["id"],
        preco_base="3.00",
    )
    tabela_cliente = client.post(
        "/v1/precificacao/tabelas",
        headers=auth(client, admin_token),
        json={"nome": "Contrato", "cliente_id": cliente["id"]},
    ).json()["data"]
    regra_cliente = _regra(
        client,
        admin_token,
        tabela_id=tabela_cliente["id"],
        produto_id=produto["id"],
        preco_base="4.00",
    )

    venda = _vender(client, admin_token, produto["id"], cliente_id=cliente["id"])
    assert venda.status_code == 200, venda.text
    item = venda.json()["data"]["itens"][0]
    assert item["valor_unitario"] == "4.00"
    assert item["regra_aplicada"]["origem"] == "tabela_cliente"
    assert item["regra_aplicada"]["regra_id"] == regra_cliente["id"]


def test_faixas_invalidas_sao_rejeitadas(client, admin_token):
    produto = _produto(client, admin_token)
    tabela = _tabela_padrao(client, admin_token)
    resp = client.post(
        "/v1/precificacao/regras",
        headers=auth(client, admin_token),
        json={
            "tabela_preco_id": tabela["id"],
            "produto_id": produto["id"],
            "preco_base": "1.00",
            "faixas": [{"qtd_min": 2, "qtd_max": 10, "preco_unitario": "1.00"}],
        },
    )
    assert resp.status_code == 422, resp.text


def test_operador_nao_cria_tabela(client, admin_token):
    login = f"op{uuid.uuid4().hex[:8]}"
    criado = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": "Operador",
            "login": login,
            "senha": "senha12345",
            "nivel_acesso": "operador",
        },
    )
    assert criado.status_code == 200, criado.text
    token = client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    ).json()["data"]["token"]
    resp = client.post(
        "/v1/precificacao/tabelas",
        headers=auth(client, token),
        json={"nome": "Não pode", "padrao": True},
    )
    assert resp.status_code == 403
