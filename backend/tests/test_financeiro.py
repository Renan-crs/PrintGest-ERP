"""Módulo Financeiro (PRD v2.0 §1.3, Fase 3) — caixa, contas a receber/pagar, plano de contas."""

import uuid
from datetime import date
from decimal import Decimal

from app.db import SessionLocal
from app.models.enums import NivelAcesso, StatusConta, TipoMovCaixa
from app.models.financeiro import ContaPagar, ContaReceber
from tests.conftest import auth

FILIAL = 1


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _token_de(client, admin_token, nivel: str) -> str:
    login, senha = f"fin{_u()}", "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": f"Usuário {nivel}",
            "login": login,
            "senha": senha,
            "nivel_acesso": nivel,
        },
    )
    assert resp.status_code == 200, resp.text
    return client.post("/v1/auth/login", json={"login": login, "senha": senha}).json()[
        "data"
    ]["token"]


def _seed_conta(usuario_id: int | None = None) -> tuple[int, int]:
    """Insere uma conta a receber e uma a pagar abertas direto no banco.

    As contas nascem dos documentos de movimento (não há endpoint de criação na
    tela Financeiro), por isso o teste semeia via sessão.
    """
    db = SessionLocal()
    try:
        receber = ContaReceber(
            filial_id=FILIAL,
            descricao=f"Parcela 1/1 — O.S. {_u()}",
            parcela=1,
            total_parcelas=1,
            vencimento=date(2026, 1, 10),
            valor=Decimal("100.00"),
            valor_pago=Decimal(0),
            status=StatusConta.ABERTA,
        )
        pagar = ContaPagar(
            filial_id=FILIAL,
            descricao=f"Compra de insumo {_u()}",
            parcela=1,
            total_parcelas=1,
            vencimento=date(2026, 1, 15),
            valor=Decimal("250.00"),
            valor_pago=Decimal(0),
            status=StatusConta.ABERTA,
        )
        db.add_all([receber, pagar])
        db.commit()
        db.refresh(receber)
        db.refresh(pagar)
        return receber.id, pagar.id
    finally:
        db.close()


# --------------------------------------------------------------------- caixa
def test_caixa_abertura_extrato_e_fechamento(client, admin_token):
    headers = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    assert (
        client.get("/v1/financeiro/caixa/atual", headers=headers).json()["data"] is None
    )

    resp = client.post(
        "/v1/financeiro/caixa/abrir", headers=headers, json={"valor_abertura": "200.00"}
    )
    assert resp.status_code == 200, resp.text
    caixa = resp.json()["data"]
    assert caixa["status"] == "aberto"
    assert Decimal(caixa["valor_abertura"]) == Decimal("200.00")
    assert Decimal(caixa["saldo_atual"]) == Decimal("200.00")

    cx = caixa["id"]
    resp = client.post(
        f"/v1/financeiro/caixa/{cx}/movimento",
        headers=headers,
        json={"tipo": "suprimento", "valor": "50.00", "descricao": "Troco"},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        f"/v1/financeiro/caixa/{cx}/movimento",
        headers=headers,
        json={"tipo": "sangria", "valor": "30.00"},
    )
    assert resp.status_code == 200, resp.text

    extrato = client.get(f"/v1/financeiro/caixa/{cx}/extrato", headers=headers).json()
    assert extrato["meta"]["total"] == 2

    atual = client.get("/v1/financeiro/caixa/atual", headers=headers).json()["data"]
    assert Decimal(atual["total_entradas"]) == Decimal("50.00")
    assert Decimal(atual["total_saidas"]) == Decimal("30.00")
    assert Decimal(atual["saldo_atual"]) == Decimal("220.00")

    fechado = client.post(
        f"/v1/financeiro/caixa/{cx}/fechar",
        headers=headers,
        json={"valor_informado": "220.00"},
    ).json()["data"]
    assert fechado["status"] == "fechado"
    assert Decimal(fechado["valor_esperado"]) == Decimal("220.00")
    assert Decimal(fechado["diferenca"]) == Decimal("0.00")
    assert (
        client.get("/v1/financeiro/caixa/atual", headers=headers).json()["data"] is None
    )


def test_fechar_caixa_registra_divergencia(client, admin_token):
    headers = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    caixa = client.post(
        "/v1/financeiro/caixa/abrir", headers=headers, json={"valor_abertura": "100.00"}
    ).json()["data"]
    fechado = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar",
        headers=headers,
        json={"valor_informado": "95.00"},
    ).json()["data"]
    assert Decimal(fechado["diferenca"]) == Decimal("-5.00")


def test_abrir_caixa_duplicado(client, admin_token):
    headers = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    client.post(
        "/v1/financeiro/caixa/abrir", headers=headers, json={"valor_abertura": "0"}
    )
    resp = client.post(
        "/v1/financeiro/caixa/abrir", headers=headers, json={"valor_abertura": "0"}
    )
    assert resp.status_code == 409
    assert "aberto" in resp.json()["detail"].lower()


def test_movimento_manual_so_sangria_suprimento(client, admin_token):
    headers = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    caixa = client.post(
        "/v1/financeiro/caixa/abrir", headers=headers, json={"valor_abertura": "0"}
    ).json()["data"]
    resp = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=headers,
        json={"tipo": TipoMovCaixa.ENTRADA.value, "valor": "10"},
    )
    assert resp.status_code == 400
    assert "sangria" in resp.json()["detail"].lower()


def test_caixa_nao_disponivel_para_operador(client, admin_token):
    token = _token_de(client, admin_token, NivelAcesso.OPERADOR.value)
    resp = client.get("/v1/financeiro/caixa/atual", headers=auth(client, token))
    assert resp.status_code == 403


# ------------------------------------------------------------- plano de contas
def test_plano_contas_crud_e_codigo_unico(client, admin_token):
    headers = auth(client, admin_token)
    codigo = f"3.{_u()}"
    resp = client.post(
        "/v1/plano-contas",
        headers=headers,
        json={"codigo": codigo, "nome": "Receita de Serviços", "tipo": "receita"},
    )
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]
    assert item["tipo"] == "receita"

    dup = client.post(
        "/v1/plano-contas",
        headers=headers,
        json={"codigo": codigo, "nome": "Outro", "tipo": "despesa"},
    )
    assert dup.status_code == 409

    lista = client.get(
        "/v1/plano-contas", headers=headers, params={"q": codigo, "tipo": "receita"}
    ).json()
    assert any(i["id"] == item["id"] for i in lista["data"])

    atualizado = client.put(
        f"/v1/plano-contas/{item['id']}", headers=headers, json={"nome": "Receitas"}
    ).json()["data"]
    assert atualizado["nome"] == "Receitas"


# -------------------------------------------------------------------- contas
def test_contas_receber_lista_e_baixa(client, admin_token):
    headers = auth(client, admin_token)
    conta_id, _ = _seed_conta()

    lista = client.get(
        "/v1/financeiro/contas-receber",
        headers=headers,
        params={"status_conta": "aberta"},
    )
    assert lista.status_code == 200, lista.text
    linha = next(i for i in lista.json()["data"] if i["id"] == conta_id)
    assert linha["status"] == "aberta"

    resp = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa",
        headers=headers,
        json={"valor_pago": "40.00", "data_pagamento": "2026-02-01"},
    )
    assert resp.status_code == 200, resp.text
    paga_parcial = resp.json()["data"]
    assert paga_parcial["status"] == "aberta"
    assert Decimal(paga_parcial["valor_pago"]) == Decimal("40.00")

    final = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa", headers=headers, json={}
    ).json()["data"]
    assert final["status"] == "paga"
    assert Decimal(final["valor_pago"]) == Decimal("100.00")

    dup = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa", headers=headers, json={}
    )
    assert dup.status_code == 409


def test_conta_receber_baixa_excede_saldo(client, admin_token):
    headers = auth(client, admin_token)
    conta_id, _ = _seed_conta()
    resp = client.post(
        f"/v1/financeiro/contas-receber/{conta_id}/baixa",
        headers=headers,
        json={"valor_pago": "999.00"},
    )
    assert resp.status_code == 400
    assert "excede" in resp.json()["detail"].lower()


def test_contas_pagar_lista_e_baixa(client, admin_token):
    headers = auth(client, admin_token)
    _, conta_id = _seed_conta()
    resp = client.post(
        f"/v1/financeiro/contas-pagar/{conta_id}/baixa", headers=headers, json={}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "paga"


def test_contas_requer_gerente(client, admin_token):
    token = _token_de(client, admin_token, NivelAcesso.CAIXA.value)
    resp = client.get("/v1/financeiro/contas-receber", headers=auth(client, token))
    assert resp.status_code == 403
