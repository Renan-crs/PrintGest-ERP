"""Regressão de layout do Orçamento: editor que quebra linha e rodapé sem corte."""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QPushButton, QScrollArea

from printgest.core.api import Api
from printgest.ui.modulos.os import PaginaOrcamento


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )
    return httpx.Response(200, json={"data": {"id": 1, "numero": 1}})


@pytest.fixture
def pagina():
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaOrcamento(api)
    pagina._novo()
    pagina.resize(1280, 720)
    pagina.show()
    return pagina


def test_editor_de_itens_nao_corta_campos_nem_botoes(app, pagina):
    app.processEvents()
    editor = pagina._itens
    viewport = pagina._painel_form.viewport()
    limite = viewport.mapTo(pagina, QPoint(viewport.width(), 0)).x()

    campos = (
        editor._combo_produto,
        editor._descricao,
        editor._qtd,
        editor._dimensoes,
        editor._vf,
        editor._unit,
        editor._desconto,
        editor._btn_adicionar,
    )
    for campo in campos:
        origem = campo.mapTo(pagina, QPoint(0, 0))
        assert origem.x() >= -1, f"campo cortado à esquerda: {campo!r}"
        assert origem.x() + campo.width() <= limite + 1, (
            f"campo cortado à direita pelo scrollbar: {campo!r}"
        )

    assert "valor_sinal" in pagina.CHAVES and "saldo" in pagina.CHAVES
    assert not pagina._painel_form.horizontalScrollBar().isVisible()


def test_estado_vazio_nao_fica_atras_do_editor(app, pagina):
    app.processEvents()
    tabela = pagina._itens._tabela
    assert tabela.rowCount() == 0
    vazio = tabela._vazio
    assert vazio.isVisible()
    assert "Nenhum item" in vazio.text()

    editor_y = pagina._itens._combo_produto.mapTo(pagina, QPoint(0, 0)).y()
    base_tabela = tabela.mapTo(pagina, QPoint(0, 0)).y() + tabela.height()
    assert editor_y >= base_tabela - 1, "editor subiu sobre a tabela/estado vazio"


def test_rodape_totais_nao_espreme_acoes(app, pagina):
    app.processEvents()
    for botao in pagina.findChildren(QPushButton):
        if not botao.isVisible():
            continue
        if botao.parent() is None or botao.parent().objectName() != "rodape":
            continue
        assert botao.width() + 1 >= botao.sizeHint().width(), (
            f"botão do rodapé cortado: {botao.text()!r}"
        )

    # ElideLabel: uma linha só, com tooltip — nunca crescendo o rodapé.
    assert not pagina._lbl_totais_os.wordWrap()
    assert pagina._lbl_totais_os.width() > 0


def test_scroll_reserva_espaco_da_barra_vertical(app, pagina):
    app.processEvents()
    rolagem = pagina.findChild(QScrollArea)
    assert rolagem is not None
    margens = rolagem.widget().layout().contentsMargins()
    assert margens.right() >= 6, "falta margem para a barra vertical"
    assert margens.bottom() >= 12, "último campo cola no rodapé"
