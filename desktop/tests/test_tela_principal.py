"""Smoke da Tela Principal: navegação v2.1, RBAC ocultando itens e banner de modo leitura."""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from printgest.core.api import Api
from printgest.ui.tela_principal import ITEM_INICIO, TelaPrincipal

_CLIENTES = [
    {"id": 1, "nome_razao": "Ana", "tipo_pessoa": "pf", "cpf_cnpj": "123", "celular": "1"},
    {"id": 2, "nome_razao": "Biz Ltda", "tipo_pessoa": "pj", "cpf_cnpj": "99", "celular": "2"},
]


def _cliente_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/clientes":
        return httpx.Response(
            200,
            json={"data": _CLIENTES, "meta": {"total": len(_CLIENTES), "limit": 50, "offset": 0}},
        )
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _principal(usuario: dict, modo_leitura: bool = False) -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_cliente_handler))
    api.autenticar({"token": "tok", "usuario": usuario})
    return TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=modo_leitura, base_url="127.0.0.1:8000"
    )


def _textos_botoes(principal):
    return [str(b.text()) for b in principal.findChildren(QPushButton)]


def test_abre_no_inicio_com_menu_visivel(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes
    assert "Projetos" in botoes
    assert "Clientes" in botoes
    assert "Configurações" in botoes  # SISTEMA só para admin


def test_caixa_ve_pdv_financeiro_e_fiscal(app):
    principal = _principal({"id": 1, "nome": "Zé", "login": "ze", "nivel_acesso": "caixa"})
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes
    assert "Financeiro" in botoes
    assert "Fiscal" in botoes
    assert "Clientes" not in botoes
    assert "Projetos" not in botoes
    assert "Fornecedores" not in botoes
    assert "Configurações" not in botoes


def test_operador_nao_ve_gestao_na_lateral(app):
    principal = _principal({"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"})
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes and "Projetos" in botoes and "Clientes" in botoes
    assert "Fornecedores" not in botoes
    assert "Financeiro" not in botoes
    assert "Fiscal" not in botoes
    assert "Configurações" not in botoes


def test_caixa_nao_tem_acesso_a_clientes(app):
    principal = _principal({"id": 1, "nome": "Zé", "login": "ze", "nivel_acesso": "caixa"})
    principal._navegar("cliente")
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio


def test_operador_nao_tem_acesso_a_financeiro(app):
    principal = _principal({"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"})
    principal._navegar("financeiro")
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio


def test_navegar_para_clientes_carrega_grade(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "operador"})
    principal._navegar("cliente")
    pumpar(lambda: principal._paginas["cliente"]._tabela.rowCount() == 2)
    assert principal._stack_paginas.currentWidget() is principal._paginas["cliente"]


def test_navegar_para_projetos_abre_listagem_de_os(app):
    # usa handler que responde 200 para /v1/os (a página de O.S. recarrega no
    # construtor; um 404 abriria QMessageBox modal e travaria o próximo pump).
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "operador"}})
    principal = TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=False, base_url="127.0.0.1:8000"
    )
    principal._navegar("projetos")
    from printgest.ui.modulos.os import PaginaProjetos

    assert isinstance(principal._stack_paginas.currentWidget(), PaginaProjetos)


def test_modo_leitura_exibe_banner(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}, modo_leitura=True
    )
    banners = [w for w in principal.findChildren(QLabel) if w.objectName() == "bannerLeitura"]
    assert len(banners) >= 1


def test_sair_emite_logout_e_limpa_sessao(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    saidas = []
    principal.solicitado_logout.connect(lambda: saidas.append(True))
    principal._sair()
    assert saidas == [True]
    assert principal._api.autenticado is False


def _vazio_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}},
    )


def test_navega_por_todo_o_menu_sem_erro(app):
    from printgest.core.rbac import MENU
    from printgest.ui.modulos.clientes import PaginaClientes
    from printgest.ui.modulos.configuracao import PaginaConfiguracoes
    from printgest.ui.modulos.financeiro import PaginaFinanceiro
    from printgest.ui.modulos.fiscal import PaginaFiscal
    from printgest.ui.modulos.fornecedores import PaginaFornecedores
    from printgest.ui.modulos.os import PaginaProjetos
    from printgest.ui.modulos.produtos import PaginaProdutos, PaginaServicos
    from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=False, base_url="127.0.0.1:8000"
    )
    esperadas = {
        "pdv": PaginaVendaBalcao,
        "projetos": PaginaProjetos,
        "cliente": PaginaClientes,
        "fornecedor": PaginaFornecedores,
        "produto": PaginaProdutos,
        "servico": PaginaServicos,
        "financeiro": PaginaFinanceiro,
        "fiscal": PaginaFiscal,
        "configuracoes": PaginaConfiguracoes,
    }
    visitadas = set()

    for _grupo, itens in MENU:
        for item in itens:
            principal._navegar(item["id"])
            pagina = principal._stack_paginas.currentWidget()
            visitadas.add(type(pagina))
            assert isinstance(pagina, esperadas[item["id"]]), item["id"]

    for esperada in esperadas.values():
        assert esperada in visitadas


def test_configuracoes_apenas_admin(app):
    gerente = _principal({"id": 1, "nome": "Ge", "login": "ge", "nivel_acesso": "gerente"})
    botoes = _textos_botoes(gerente)
    assert "Configurações" not in botoes
    gerente._navegar("configuracoes")
    assert gerente._stack_paginas.currentWidget() is gerente._pagina_inicio