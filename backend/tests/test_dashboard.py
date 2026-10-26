"""Dashboard (Tela Inicial) — resumo do dia: vendas, O.S., estoque, a receber.

Valida o `GET /v1/dashboard/resumo`:
  - qualquer usuário autenticado acessa;
  - campos operacionais (`projetos_*`, `entregas_hoje`, `estoque_abaixo_minimo`)
    só aparecem preenchidos para OPERADOR+ (RBAC server-side);
  - campos gerenciais (`a_receber_*`, `faturamento_previsto`, `vendas_7_dias`)
    só aparecem preenchidos para ADMIN/GERENTE e vêm `null` para CAIXA;
  - `dias` controla a janela das séries (7/30);
  - sem token → 401.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.models.enums import NivelAcesso
from tests.conftest import auth


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_cliente(client, token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, token),
        json={"nome_razao": f"Cliente Dash {_u()}", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_venda(client, token, data: date | None = None):
    payload = {
        "forma_pagamento": "dinheiro",
        "parcelas": 1,
        "itens": [
            {
                "produto_id": None,
                "descricao_avulsa": "Impressão colorida A4",
                "quantidade": 2,
                "valor_unitario": 12.50,
            }
        ],
    }
    if data is not None:
        payload["data_venda"] = data.isoformat()
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, token),
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_os(client, token, cliente, previsao: date | None = None):
    payload = {
        "tipo": "os",
        "cliente_id": cliente["id"],
        "itens": [
            {
                "produto_id": None,
                "descricao_avulsa": "Corte e vinco A4",
                "quantidade": 100,
                "valor_unitario": 0.5,
                "dimensoes": "21x29,7",
            }
        ],
    }
    if previsao is not None:
        payload["data_previsao_entrega"] = previsao.isoformat()
    resp = client.post(
        "/v1/os",
        headers=auth(client, token),
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _avancar_os(client, token, os_id, statuses):
    for status in statuses:
        resp = client.patch(
            f"/v1/os/{os_id}/status",
            headers=auth(client, token),
            json={"status": status},
        )
        assert resp.status_code == 200, resp.text


def _criar_produto_critico(client, token):
    resp = client.post(
        "/v1/produtos",
        headers=auth(client, token),
        json={
            "codigo": f"DASH{uuid.uuid4().hex[:8].upper()}",
            "nome": "Papel Sulfite A4",
            "tipo": "produto",
            "unidade": "resma",
            "preco_custo": 15.0,
            "preco_venda": 29.9,
            "estoque_minimo": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_conta_receber(vencimento: date, valor: Decimal, valor_pago: Decimal = Decimal("0")):
    """Cria `conta_receber` diretamente no banco de teste (não há API ainda)."""
    from app.db import SessionLocal
    from app.models.core import Usuario
    from app.models.financeiro import ContaReceber

    sessao = SessionLocal()
    try:
        filial_id = (
            sessao.query(Usuario).filter(Usuario.login == "admin").first().filial_id or 1
        )
        conta = ContaReceber(
            filial_id=filial_id,
            descricao=f"CR Dash {_u()}",
            vencimento=vencimento,
            valor=valor,
            valor_pago=valor_pago,
        )
        sessao.add(conta)
        sessao.commit()
        sessao.refresh(conta)
        return conta.id
    finally:
        sessao.close()


def _resumo(client, token, dias: int | None = None):
    url = "/v1/dashboard/resumo"
    if dias is not None:
        url += f"?dias={dias}"
    resp = client.get(url, headers=auth(client, token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_usuario(client, admin_token, nivel: NivelAcesso):
    login, senha = f"u{uuid.uuid4().hex[:8]}", "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": f"Usuário Dash {nivel.value}", "login": login,
              "senha": senha, "nivel_acesso": nivel.value},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post("/v1/auth/login", json={"login": login, "senha": senha})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_resumo_dashboard_admin_agrega_dados_reais(client, admin_token):
    hoje = date.today()
    base = _resumo(client, admin_token)
    cliente = _criar_cliente(client, admin_token)
    _criar_venda(client, admin_token)
    _criar_venda(client, admin_token, data=hoje - timedelta(days=1))
    _criar_conta_receber(hoje, Decimal("100.00"))
    _criar_conta_receber(hoje - timedelta(days=3), Decimal("50.00"), valor_pago=Decimal("10.00"))

    os_producao = _criar_os(client, admin_token, cliente, previsao=hoje + timedelta(days=5))
    _avancar_os(client, admin_token, os_producao["id"], ["producao"])
    os_atrasada = _criar_os(client, admin_token, cliente, previsao=hoje - timedelta(days=2))
    os_hoje = _criar_os(client, admin_token, cliente, previsao=hoje)
    _criar_produto_critico(client, admin_token)

    dados = _resumo(client, admin_token)

    assert dados["filial_nome"] == "Matriz"
    assert dados["vendas_hoje_qtd"] == base["vendas_hoje_qtd"] + 1
    assert Decimal(dados["vendas_hoje_valor"]) == Decimal(base["vendas_hoje_valor"]) + Decimal("25.00")
    # compare com ontem
    assert dados["vendas_ontem_qtd"] == base["vendas_ontem_qtd"] + 1
    assert Decimal(dados["vendas_ontem_valor"]) == Decimal(base["vendas_ontem_valor"]) + Decimal("25.00")

    # campos operacionais preenchidos para ADMIN.
    assert dados["estoque_abaixo_minimo"] is not None
    assert dados["estoque_abaixo_minimo"] >= 1
    assert dados["projetos_em_producao"] == base["projetos_em_producao"] + 1
    assert dados["projetos_atrasados"] == base["projetos_atrasados"] + 1

    # a receber: saldo em aberto (valor − pago), gerencial.
    assert Decimal(dados["a_receber_vence_hoje"]) == Decimal(base["a_receber_vence_hoje"]) + Decimal("100.00")
    assert Decimal(dados["a_receber_atrasado"]) == Decimal(base["a_receber_atrasado"]) + Decimal("40.00")

    # entregas do dia: as 2 O.S. com prazo <= hoje, atrasada sinalizada.
    entregas = dados["entregas_hoje"]
    assert isinstance(entregas, list)
    entregas_por_os = {e["os_id"]: e for e in entregas}
    assert entregas_por_os[os_atrasada["id"]]["atrasada"] is True
    assert entregas_por_os[os_atrasada["id"]]["cliente_nome"] == cliente["nome_razao"]
    assert entregas_por_os[os_atrasada["id"]]["servico"] == "Corte e vinco A4"
    assert entregas_por_os[os_hoje["id"]]["atrasada"] is False
    assert entregas_por_os[os_hoje["id"]]["status"] == "aberto"
    assert "numero" in entregas_por_os[os_hoje["id"]]

    # série de 7 dias e previsto 7 dias por padrão.
    assert isinstance(dados["vendas_7_dias"], list)
    assert len(dados["vendas_7_dias"]) == 7
    assert Decimal(dados["vendas_7_dias"][-1]["valor"]) == Decimal(base["vendas_7_dias"][-1]["valor"]) + Decimal("25.00")

    previsto = dados["faturamento_previsto"]
    base_previsto = base["faturamento_previsto"]
    assert isinstance(previsto, list)
    assert len(previsto) == 7
    # a conta que vence hoje entra no primeiro dia do previsto.
    assert Decimal(previsto[0]["valor"]) == Decimal(base_previsto[0]["valor"]) + Decimal("100.00")


def test_resumo_dashboard_dias_30_estende_series(client, admin_token):
    dados7 = _resumo(client, admin_token, dias=7)
    dados30 = _resumo(client, admin_token, dias=30)
    assert len(dados30["vendas_7_dias"]) == 30
    assert len(dados30["faturamento_previsto"]) == 30
    assert len(dados7["vendas_7_dias"]) == 7
    assert dados7["vendas_7_dias"][-1]["data"] == dados30["vendas_7_dias"][-1]["data"]


def test_resumo_dashboard_operador_ve_operacional_mas_nao_gerencial(client, admin_token):
    base = _resumo(client, admin_token)
    token_operador = _criar_usuario(client, admin_token, NivelAcesso.OPERADOR)

    dados = _resumo(client, token_operador)

    assert dados["vendas_hoje_qtd"] == base["vendas_hoje_qtd"]
    # operacional visível para OPERADOR.
    assert dados["projetos_em_producao"] is not None
    assert dados["projetos_atrasados"] is not None
    assert dados["estoque_abaixo_minimo"] is not None
    assert dados["entregas_hoje"] is not None
    # gerencial oculto para OPERADOR.
    assert dados["a_receber_vence_hoje"] is None
    assert dados["a_receber_atrasado"] is None
    assert dados["faturamento_previsto"] is None
    assert dados["vendas_7_dias"] is None


def test_resumo_dashboard_caixa_esconde_campos_operacionais_e_gerenciais(
    client, admin_token
):
    base_admin = _resumo(client, admin_token)
    _criar_venda(client, admin_token)

    token_caixa = _criar_usuario(client, admin_token, NivelAcesso.CAIXA)
    dados = _resumo(client, token_caixa)

    assert dados["filial_nome"] == "Matriz"
    assert dados["vendas_hoje_qtd"] == base_admin["vendas_hoje_qtd"] + 1
    # RBAC server-side: caixa não vê operacional nem gerencial.
    assert dados["projetos_em_producao"] is None
    assert dados["projetos_atrasados"] is None
    assert dados["entregas_hoje"] is None
    assert dados["estoque_abaixo_minimo"] is None
    assert dados["a_receber_vence_hoje"] is None
    assert dados["a_receber_atrasado"] is None
    assert dados["faturamento_previsto"] is None
    assert dados["vendas_7_dias"] is None


def test_resumo_dashboard_sem_token_401(client):
    resp = client.get("/v1/dashboard/resumo")
    assert resp.status_code == 401