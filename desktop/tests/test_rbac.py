"""Testes do RBAC do menu v2.1 (`printgest.core.rbac`).

Cobre a matriz não hierárquica do PRD v2.1 §1.1 (caixa vê Financeiro/Fiscal,
operador não) e o helper `pode_abrir` dos itens internos fora do menu.
"""

from __future__ import annotations

from printgest.core.rbac import (
    ID_MENU,
    ITENS_INTERNOS,
    MENU,
    menu_visivel,
    pode_abrir,
    rotulo_do_item,
    tem_acesso,
)


def test_hierarquia_de_niveis():
    assert tem_acesso("admin", "caixa")
    assert tem_acesso("gerente", "operador")
    assert tem_acesso("operador", "caixa")
    assert not tem_acesso("caixa", "operador")
    assert not tem_acesso("operador", "gerente")


def test_menu_v21_tem_nove_ids_com_niveis_explícitos():
    ids = {i["id"] for _g, itens in MENU for i in itens}
    assert ids == {
        "pdv",
        "projetos",
        "agendamento",
        "cliente",
        "fornecedor",
        "produto",
        "servico",
        "categoria",
        "funcionario",
        "financeiro",
        "fiscal",
        "estoque",
        "relatorios",
        "configuracoes",
    }
    grupos = [_g for _g, _itens in MENU]
    assert grupos == ["Operação", "Cadastros", "Gestão", "Relatórios", "Sistema"]
    for _grupo, itens in MENU:
        for item in itens:
            assert isinstance(item.get("niveis"), list) and item["niveis"]


def test_matriz_nao_hierarquica_caixa_ve_financeiro_e_fiscal():
    menu = dict((grupo, [i["id"] for i in itens]) for grupo, itens in menu_visivel("caixa"))
    assert menu == {"Operação": ["pdv"], "Gestão": ["financeiro", "fiscal"]}


def test_operador_ve_operacao_e_cadastros_mas_nao_gestao():
    ids = {i["id"] for _g, itens in menu_visivel("operador") for i in itens}
    assert ids == {
        "pdv",
        "projetos",
        "agendamento",
        "cliente",
        "produto",
        "servico",
        "categoria",
        "funcionario",
        "estoque",
    }
    assert "fornecedor" not in ids
    assert "financeiro" not in ids and "fiscal" not in ids
    assert "relatorios" not in ids
    assert "configuracoes" not in ids


def test_gerente_ve_gestao_e_cadastros_completos():
    ids = {i["id"] for _g, itens in menu_visivel("gerente") for i in itens}
    assert {
        "fornecedor",
        "financeiro",
        "fiscal",
        "estoque",
        "relatorios",
        "pdv",
        "projetos",
        "agendamento",
    } <= ids
    assert "configuracoes" not in ids


def test_admin_ve_tudo():
    ids = {i["id"] for _g, itens in menu_visivel("admin") for i in itens}
    assert ids == ID_MENU


def test_pode_abrir_itens_internos():
    assert pode_abrir("operador", "os")
    assert pode_abrir("operador", "estoque_consulta")
    assert pode_abrir("operador", "orcamento")
    assert pode_abrir("caixa", "venda_balcao")
    assert pode_abrir("gerente", "contas_receber")
    assert pode_abrir("gerente", "rel_vendas")
    assert pode_abrir("admin", "usuarios")
    assert pode_abrir("admin", "reajuste_bloco")
    # barreiras
    assert not pode_abrir("operador", "financeiro")
    assert not pode_abrir("operador", "configuracoes")
    assert not pode_abrir("operador", "contas_receber")
    assert not pode_abrir("operador", "rel_vendas")
    assert not pode_abrir("operador", "usuarios")
    assert not pode_abrir("caixa", "os")
    assert not pode_abrir("caixa", "cliente")
    assert not pode_abrir("forasteiro", "pdv")
    assert not pode_abrir("inicio", "nao_existe")


def test_rotulo_do_item_acha_menu_e_internos():
    assert rotulo_do_item("pdv") == "PDV"
    assert rotulo_do_item("configuracoes") == "Configurações"
    assert rotulo_do_item("os") == "Ordem de Serviço"
    assert rotulo_do_item("relatorios") == "Relatórios"
    assert rotulo_do_item("desconhecido") == "desconhecido"


def test_ids_internos_e_menu_nao_colidem():
    internos = {i["id"] for i in ITENS_INTERNOS}
    assert ID_MENU.isdisjoint(internos)
    for item in ITENS_INTERNOS:
        assert item["id"] and item["rotulo"] and item["nivel"]