"""Integração do motor de preço em venda/orçamento/OS (guia V0, sem migration).

Prova que:
- com `regra_preco`, o servidor calcula e **ignora** o `valor_unitario` enviado;
- sem regra, o comportamento legado permanece intacto (compatibilidade);
- itens de fornecedor continuam soberanos da cotação;
- a explicação volta na resposta, mas não sobrevive a um GET (limitação da fase).
"""

from __future__ import annotations

import uuid

from tests.conftest import auth


def _faixas() -> list[dict]:
    return [
        {"qtd_min": 1, "qtd_max": 49, "preco_unitario": "1.00"},
        {"qtd_min": 50, "qtd_max": 199, "preco_unitario": "0.80"},
        {"qtd_min": 200, "qtd_max": None, "preco_unitario": "0.60"},
    ]


def _regra() -> dict:
    return {"faixas": _faixas()}


def _cliente(client, token) -> dict:
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, token),
        json={
            "nome_razao": f"Cliente Preco {uuid.uuid4().hex[:8]}",
            "tipo_pessoa": "pf",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _item_com_regra(**extra) -> dict:
    item = {
        "descricao_avulsa": "Impressão sulfite A4",
        "quantidade": 120,
        # Valor inflado de propósito: o servidor não pode confiar nele.
        "valor_unitario": "999.00",
        "regra_preco": _regra(),
    }
    item.update(extra)
    return item


# --------------------------------------------------------------- venda


def test_venda_com_regra_usa_o_motor(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={"forma_pagamento": "dinheiro", "itens": [_item_com_regra()]},
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    item = dados["itens"][0]
    assert item["valor_unitario"] == "0.80"
    assert item["valor_total"] == "96.00"
    assert dados["valor_total"] == "96.00"
    assert any("Faixa 50-199" in linha for linha in item["explicacao"])


def test_venda_sem_regra_mantem_comportamento_legado(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                {
                    "descricao_avulsa": "Serviço avulso",
                    "quantidade": 3,
                    "valor_unitario": "20.00",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    assert item["valor_unitario"] == "20.00"
    assert item["valor_total"] == "60.00"
    assert item["explicacao"] == []


def test_venda_regra_sem_preco_400(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [_item_com_regra(regra_preco={})],
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["codigo"] == "PRECO_NAO_CADASTRADO"


def test_venda_regra_com_quantidade_fracionaria_422(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [_item_com_regra(quantidade="2.5")],
        },
    )
    assert resp.status_code == 422, resp.text
    assert "inteira" in resp.json()["detail"].lower()


def test_venda_regra_respeita_desconto_do_item(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [_item_com_regra(desconto="6.00")],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["itens"][0]["valor_total"] == "90.00"


def test_venda_com_regra_e_minimo_por_linha(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                _item_com_regra(
                    quantidade=1,
                    regra_preco={"preco_base": "1.00", "minimo": "5.00"},
                )
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    # Total do motor (com mínimo), não unitário arredondado × quantidade.
    assert item["valor_unitario"] == "1.00"
    assert item["valor_total"] == "5.00"


def test_venda_multiplos_itens_com_regras(client, admin_token, caixa_admin):
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "forma_pagamento": "dinheiro",
            "itens": [
                _item_com_regra(descricao_avulsa="Sulfite"),
                _item_com_regra(
                    descricao_avulsa="Alta alvura",
                    quantidade=10,
                    regra_preco={"preco_base": "8.00"},
                ),
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert [i["valor_total"] for i in dados["itens"]] == ["96.00", "80.00"]
    assert dados["valor_total"] == "176.00"


# --------------------------------------------------------------- OS / orçamento


def test_os_com_regra_usa_o_motor_e_devolve_explicacao(client, admin_token):
    cliente = _cliente(client, admin_token)
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={"tipo": "os", "cliente_id": cliente["id"], "itens": [_item_com_regra()]},
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    item = dados["itens"][0]
    assert item["valor_unitario"] == "0.80"
    assert item["valor_total"] == "96.00"
    assert dados["valor_total"] == "96.00"
    assert any("Faixa 50-199" in linha for linha in item["explicacao"])


def test_orcamento_com_regra_usa_o_motor(client, admin_token):
    cliente = _cliente(client, admin_token)
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "orcamento",
            "cliente_id": cliente["id"],
            "itens": [_item_com_regra()],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["valor_total"] == "96.00"


def test_os_item_fornecedor_ignora_a_regra(client, admin_token):
    cliente = _cliente(client, admin_token)
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                _item_com_regra(
                    tipo="fornecedor", valor_unitario="7.00", quantidade=2
                )
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["itens"][0]
    # Preço do terceirizado pertence à cotação, não ao motor de variações.
    assert item["valor_unitario"] == "7.00"
    assert item["valor_total"] == "14.00"


def test_put_os_recalcula_quando_regra_e_enviada(client, admin_token):
    cliente = _cliente(client, admin_token)
    criado = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "descricao_avulsa": "Item legado",
                    "quantidade": 1,
                    "valor_unitario": "10.00",
                }
            ],
        },
    )
    assert criado.status_code == 200, criado.text
    os_id = criado.json()["data"]["id"]
    item_id = criado.json()["data"]["itens"][0]["id"]

    resp = client.put(
        f"/v1/os/{os_id}",
        headers=auth(client, admin_token),
        json={
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "id": item_id,
                    "descricao_avulsa": "Item legado",
                    "quantidade": 120,
                    "valor_unitario": "999.00",
                    "regra_preco": _regra(),
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["valor_total"] == "96.00"


def test_explicacao_e_transiente_nao_sobrevive_ao_get(client, admin_token):
    cliente = _cliente(client, admin_token)
    criado = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={"tipo": "os", "cliente_id": cliente["id"], "itens": [_item_com_regra()]},
    )
    assert criado.status_code == 200, criado.text
    assert criado.json()["data"]["itens"][0]["explicacao"]

    os_id = criado.json()["data"]["id"]
    consultado = client.get(f"/v1/os/{os_id}", headers=auth(client, admin_token))
    assert consultado.status_code == 200, consultado.text
    # Limitação desta fase: sem regra persistida não há como reconstruir.
    assert consultado.json()["data"]["itens"][0]["explicacao"] == []
    # O preço calculado continua gravado corretamente.
    assert consultado.json()["data"]["valor_total"] == "96.00"
