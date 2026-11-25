"""Fase V2 — ficha de consumo, custo/margem e baixa real de insumos."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.conftest import arte_aprovada, auth


def D(v: str) -> Decimal:
    return Decimal(v)


def _produto(client, token, *, tipo: str = "produto", controla: bool = True, **extra):
    payload = {
        "codigo": f"PR{uuid.uuid4().hex[:10].upper()}",
        "nome": f"Produto {uuid.uuid4().hex[:6]}",
        "tipo": tipo,
        "unidade": "un",
        "controla_estoque": controla,
        "preco_venda": "20.00",
    }
    if tipo == "produto":
        payload["preco_custo"] = "2.00"
    payload.update(extra)
    resp = client.post("/v1/produtos", headers=auth(client, token), json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _cliente(client, token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, token),
        json={
            "nome_razao": f"Cliente V2 {uuid.uuid4().hex[:6]}",
            "tipo_pessoa": "pf",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _ficha(client, token, produto_id, insumo_id, **extra):
    payload = {
        "produto_id": produto_id,
        "insumo_id": insumo_id,
        "quantidade_por_unidade": "2",
        "perda_percentual": "10",
        "custo_processo_unitario": "1",
    }
    payload.update(extra)
    resp = client.post(
        "/v1/producao/fichas", headers=auth(client, token), json=payload
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _entrada(client, token, produto_id, quantidade):
    resp = client.post(
        "/v1/estoque/movimentar",
        headers=auth(client, token),
        json={"produto_id": produto_id, "tipo": "entrada", "quantidade": quantidade},
    )
    assert resp.status_code == 200, resp.text


def _saldo(client, token, produto_id) -> Decimal:
    """Saldo pelo kardex (mais recente primeiro) — não depende de paginação."""
    resp = client.get(
        f"/v1/estoque/{produto_id}/kardex",
        headers=auth(client, token),
        params={"limit": 100},
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    return Decimal(dados[0]["saldo_posterior"]) if dados else Decimal("0")


# ------------------------------------------------------------------- cálculo puro


def test_calculo_de_custo_com_perda_e_processo():
    from app.services.custo_service import calcular_custo_unitario

    fichas = [
        SimpleNamespace(
            id=1, insumo_id=10, quantidade_por_unidade=D("2"),
            perda_percentual=D("10"), custo_processo_unitario=D("1"),
        ),
        SimpleNamespace(
            id=2, insumo_id=11, quantidade_por_unidade=D("0.5"),
            perda_percentual=D("0"), custo_processo_unitario=D("1"),
        ),
    ]
    custos = {10: D("2.00"), 11: D("4.00")}
    custo, consumo, alertas = calcular_custo_unitario(fichas, custos)
    # 2 × 1,1 × 2,00 = 4,40; 0,5 × 4,00 = 2,00; + processo 1,00 (uma vez)
    assert custo == D("7.4000")
    assert len(consumo) == 2
    assert alertas == []


def test_margem_bruta():
    from app.services.custo_service import calcular_margem_bruta

    assert calcular_margem_bruta(D("20"), D("5.4")) == D("0.7300")
    assert calcular_margem_bruta(D("0"), D("1")) is None


# ------------------------------------------------------------------- ficha e custo


def test_criar_ficha_e_consultar_custo(client, admin_token):
    servico = _produto(client, admin_token, tipo="servico", controla=False)
    insumo = _produto(client, admin_token)
    _ficha(client, admin_token, servico["id"], insumo["id"])

    resp = client.get(
        f"/v1/producao/produtos/{servico['id']}/custo",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    # 2 × 1,1 × 2,00 + 1,00 = 5,40; margem (20 − 5,4)/20 = 73%
    assert dados["custo_unitario"] == "5.4000"
    assert dados["margem_bruta"] == "0.7300"
    assert dados["consumo_previsto"][0]["insumo_id"] == insumo["id"]


def test_ficha_rejeita_insumo_servico(client, admin_token):
    servico = _produto(client, admin_token, tipo="servico", controla=False)
    insumo_servico = _produto(client, admin_token, tipo="servico", controla=False)
    resp = client.post(
        "/v1/producao/fichas",
        headers=auth(client, admin_token),
        json={
            "produto_id": servico["id"],
            "insumo_id": insumo_servico["id"],
            "quantidade_por_unidade": "1",
        },
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("perda", ["-1", "101"])
def test_ficha_rejeita_perda_invalida(client, admin_token, perda):
    servico = _produto(client, admin_token, tipo="servico", controla=False)
    insumo = _produto(client, admin_token)
    resp = client.post(
        "/v1/producao/fichas",
        headers=auth(client, admin_token),
        json={
            "produto_id": servico["id"],
            "insumo_id": insumo["id"],
            "quantidade_por_unidade": "1",
            "perda_percentual": perda,
        },
    )
    assert resp.status_code == 422


def test_operador_nao_cria_ficha(client, admin_token):
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
        "/v1/producao/fichas",
        headers=auth(client, token),
        json={"produto_id": 1, "insumo_id": 2, "quantidade_por_unidade": "1"},
    )
    assert resp.status_code == 403


# --------------------------------------------------------------- produção / baixa


def _os_com_ficha(client, token, *, quantidade=10):
    servico = _produto(client, token, tipo="servico", controla=False)
    insumo = _produto(client, token)
    _ficha(client, token, servico["id"], insumo["id"])
    cliente = _cliente(client, token)
    criada = client.post(
        "/v1/os",
        headers=auth(client, token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "produto_id": servico["id"],
                    "quantidade": quantidade,
                    "valor_unitario": "20.00",
                }
            ],
        },
    )
    assert criada.status_code == 200, criada.text
    return criada.json()["data"], insumo


def _iniciar_producao(client, token, os_id):
    arte_aprovada(client, token, os_id)
    resp = client.patch(
        f"/v1/os/{os_id}/status",
        headers=auth(client, token),
        json={"status": "producao"},
    )
    assert resp.status_code == 200, resp.text


def test_consumo_previsto_ao_iniciar_producao(client, admin_token):
    os_obj, insumo = _os_com_ficha(client, admin_token)
    os_id, item_id = os_obj["id"], os_obj["itens"][0]["id"]
    _iniciar_producao(client, admin_token, os_id)

    resp = client.get(
        f"/v1/producao/os/{os_id}/itens/{item_id}/consumo",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert len(dados) == 1
    # 2 unidades × 1,1 × 10 itens = 22,000
    assert dados[0]["insumo_id"] == insumo["id"]
    assert Decimal(dados[0]["quantidade_prevista"]) == D("22.000")
    assert dados[0]["baixado_em"] is None


def test_baixa_real_atomica_kardex_e_idempotencia(client, admin_token):
    os_obj, insumo = _os_com_ficha(client, admin_token)
    os_id, item_id = os_obj["id"], os_obj["itens"][0]["id"]
    _iniciar_producao(client, admin_token, os_id)
    _entrada(client, admin_token, insumo["id"], 100)
    saldo_antes = _saldo(client, admin_token, insumo["id"])

    resp = client.post(
        f"/v1/producao/os/{os_id}/itens/{item_id}/baixar-consumo",
        headers=auth(client, admin_token),
        json={"motivo_perda": "Acerto de máquina"},
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["data"][0]["quantidade_real"]) == D("22.000")
    assert _saldo(client, admin_token, insumo["id"]) == saldo_antes - D("22")

    kardex = client.get(
        f"/v1/estoque/{insumo['id']}/kardex", headers=auth(client, admin_token)
    ).json()
    saidas = [m for m in kardex["data"] if m["origem"] == "ordem_servico"]
    assert saidas
    assert saidas[0]["tipo"] == "saida"
    assert Decimal(saidas[0]["quantidade"]) == D("-22.000")
    assert saidas[0]["documento_id"] == item_id

    # Item marcado como executado (nunca era escrito antes desta entrega).
    detalhe = client.get(
        f"/v1/os/{os_id}", headers=auth(client, admin_token)
    ).json()["data"]
    assert detalhe["itens"][0]["executado"] is True

    # Segunda chamada não duplica o kardex.
    repetida = client.post(
        f"/v1/producao/os/{os_id}/itens/{item_id}/baixar-consumo",
        headers=auth(client, admin_token),
        json={},
    )
    assert repetida.status_code == 409
    assert _saldo(client, admin_token, insumo["id"]) == saldo_antes - D("22")


def test_baixa_sem_saldo_nao_debita_nada(client, admin_token):
    os_obj, insumo = _os_com_ficha(client, admin_token)
    os_id, item_id = os_obj["id"], os_obj["itens"][0]["id"]
    _iniciar_producao(client, admin_token, os_id)
    # Sem entrada de estoque: saldo 0.

    resp = client.post(
        f"/v1/producao/os/{os_id}/itens/{item_id}/baixar-consumo",
        headers=auth(client, admin_token),
        json={},
    )
    assert resp.status_code == 409
    assert _saldo(client, admin_token, insumo["id"]) == D("0")


def test_baixa_com_quantidade_real_override(client, admin_token):
    os_obj, insumo = _os_com_ficha(client, admin_token)
    os_id, item_id = os_obj["id"], os_obj["itens"][0]["id"]
    _iniciar_producao(client, admin_token, os_id)
    _entrada(client, admin_token, insumo["id"], 100)
    saldo_antes = _saldo(client, admin_token, insumo["id"])

    resp = client.post(
        f"/v1/producao/os/{os_id}/itens/{item_id}/baixar-consumo",
        headers=auth(client, admin_token),
        json={"quantidades": {str(insumo["id"]): "5"}},
    )
    assert resp.status_code == 200, resp.text
    assert _saldo(client, admin_token, insumo["id"]) == saldo_antes - D("5")


def test_item_avulso_sem_ficha_nao_cria_consumo(client, admin_token):
    cliente = _cliente(client, admin_token)
    criada = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "descricao_avulsa": "Serviço avulso",
                    "quantidade": 1,
                    "valor_unitario": "50.00",
                }
            ],
        },
    )
    assert criada.status_code == 200, criada.text
    os_id = criada.json()["data"]["id"]
    arte_aprovada(client, admin_token, os_id)
    resp = client.patch(
        f"/v1/os/{os_id}/status",
        headers=auth(client, admin_token),
        json={"status": "producao"},
    )
    assert resp.status_code == 200, resp.text
    consumo = client.get(
        f"/v1/producao/os/{os_id}/itens/{criada.json()['data']['itens'][0]['id']}/consumo",
        headers=auth(client, admin_token),
    )
    assert consumo.json()["data"] == []
