"""Auditoria visual P3: a janela deve caber em 1024x768 em todas as telas.

Regressões já vistas e cobertas aqui:
  - cabeçalho/rodapé com QLabel's de largura fixa travavam a janela em ~1248px;
  - o QStackedWidget do PDV propagava a largura da grade do Histórico (~2096px);
  - filtros do CRUD empilhados numa coluna estreita em 1024px.
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollBar

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal


def _handler(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if caminho == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if caminho == "/v1/licenca":
        dados = {"status": "ativa", "modo_leitura": False}
    elif caminho == "/v1/dashboard/resumo":
        dados = {
            "filial_nome": "Matriz", "vendas_hoje_qtd": 0, "vendas_hoje_valor": "0",
            "vendas_ontem_qtd": 0, "vendas_ontem_valor": "0",
            "projetos_em_producao": 0, "projetos_atrasados": 0,
            "a_receber_vence_hoje": "0", "a_receber_atrasado": "0",
            "estoque_abaixo_minimo": 0, "entregas_hoje": [],
            "vendas_7_dias": [], "faturamento_previsto": [],
        }
    else:
        dados = []
    return httpx.Response(
        200,
        json={"data": dados, "meta": {"total": len(dados) if isinstance(dados, list) else 1,
                                       "limit": 50, "offset": 0}},
    )


def _principal() -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {
        "id": 1, "nome": "Maria Silva", "login": "maria",
        "nivel_acesso": "admin", "filial_nome": "Matriz",
    }})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    principal.show()
    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()
    principal.resize(1024, 768)
    for _ in range(10):
        app.processEvents()
    return principal


@pytest.mark.parametrize("pagina", ["inicio", "pdv", "os", "cliente", "produto"])
def test_tela_cabe_em_1024x768(app, pagina):
    principal = _principal()
    assert principal.width() == 1024
    assert principal.height() == 768

    principal._navegar(pagina)
    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()
    assert principal.width() == 1024, f"{pagina} forçou largura {principal.width()}"
    assert principal.height() == 768


def test_sem_rolagem_horizontal_em_1024(app):
    principal = _principal()
    principal._navegar("pdv")
    pagina = principal._paginas["pdv"]
    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()
    pagina._ir_para_historico()
    app.processEvents()
    for tabela in (pagina._tabela, pagina._itens_editor._tabela):
        assert tabela.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert not tabela.horizontalScrollBar().isVisible()
    for barra in principal.findChildren(QScrollBar):
        if barra.orientation() == Qt.Orientation.Horizontal:
            assert not barra.isVisible(), f"rolagem horizontal visível: {barra.parent()!r}"


def test_filtros_da_os_ocupam_a_largura(app):
    principal = _principal()
    principal._navegar("os")
    app = QApplication.instance()
    app.processEvents()
    pagina = principal._paginas["os"]
    filtros = pagina._filtros_widget
    assert filtros is not None
    assert abs(filtros.width() - pagina._busca.width()) < 24, (
        f"filtros com {filtros.width()}px vs busca {pagina._busca.width()}px"
    )
