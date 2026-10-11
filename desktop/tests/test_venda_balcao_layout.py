"""Auditoria de layout do PDV: sem rolagem horizontal e ação sempre visível.

Roda a Tela Principal em 1280x720, 1366x768 e 1920x1080 (offscreen) já na visão
"Nova venda" e verifica, programaticamente, os critérios de aceite:

  - nenhuma rolagem horizontal nas grades do PDV;
  - a visão "Nova venda" não contém `QScrollArea` (nada de rolagem aninhada);
  - o botão "Finalizar venda" fica inteiro dentro da janela em qualquer tamanho;
  - rótulos e campos não são cortados verticalmente.
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QPushButton,
    QScrollArea,
)

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal

_RESOLUCOES = [(1280, 720), (1366, 768), (1920, 1080), (960, 540), (853, 480)]

_VENDA = {
    "id": 10,
    "numero": 2894,
    "status": "ok",
    "cliente_id": None,
    "cliente_nome": "Gráfica Impressos Comunicação Visual Ltda ME",
    "vendedor_id": None,
    "forma_pagamento": "pix",
    "parcelas": 1,
    "data_venda": "2026-09-23",
    "desconto": "0",
    "valor_itens": "123456.78",
    "valor_total": "123456.78",
    "itens": [],
}


def _handler(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if caminho == "/v1/vendas":
        return httpx.Response(
            200, json={"data": [_VENDA], "meta": {"total": 1, "limit": 50, "offset": 0}}
        )
    if caminho == "/v1/clientes":
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1, "nome_razao": "Ana Maria de Souza Oliveira"}],
                "meta": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    if caminho == "/v1/funcionarios":
        return httpx.Response(
            200,
            json={
                "data": [{"id": 10, "nome": "Vina", "e_vendedor": True}],
                "meta": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    if caminho == "/v1/produtos":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 5,
                        "codigo": "B015",
                        "nome": "Adesivo Frosted 3mm Poster",
                        "preco_venda": "123456.78",
                    }
                ],
                "meta": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    if caminho == "/v1/dashboard/resumo":
        return httpx.Response(
            200,
            json={
                "data": {
                    "filial_nome": "Matriz",
                    "vendas_hoje_qtd": 0,
                    "vendas_hoje_valor": "0",
                    "vendas_ontem_qtd": 0,
                    "vendas_ontem_valor": "0",
                    "projetos_em_producao": 0,
                    "projetos_atrasados": 0,
                    "a_receber_vence_hoje": "0",
                    "a_receber_atrasado": "0",
                    "estoque_abaixo_minimo": 0,
                    "entregas_hoje": [],
                    "vendas_7_dias": [],
                    "faturamento_previsto": [],
                }
            },
        )
    if caminho == "/v1/licenca":
        return httpx.Response(
            200, json={"data": {"status": "ativa", "modo_leitura": False}}
        )
    if caminho == "/health":
        return httpx.Response(200, json={"status": "ok"})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pdv(pumpar):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar(
        {
            "token": "tok",
            "usuario": {
                "id": 1,
                "nome": "Maria Silva",
                "login": "maria",
                "nivel_acesso": "admin",
                "filial_nome": "Matriz",
            },
        }
    )
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    # Permite reproduzir telas lógicas pequenas (ex.: 1280x720 a 150% → 853x480).
    principal.setMinimumSize(0, 0)
    principal._navegar("pdv")
    pagina = principal._paginas["pdv"]
    pumpar(lambda: pagina._total == 1)
    return principal, pagina


@pytest.mark.parametrize("largura,altura", _RESOLUCOES)
def test_pdv_sem_rolagem_horizontal_e_acao_visivel(app, pumpar, largura, altura):
    principal, pagina = _pdv(pumpar)
    principal.resize(largura, altura)
    principal.show()
    app.processEvents()

    # 1) nenhuma grade rola na horizontal.
    for tabela in (pagina._tabela, pagina._itens_editor._tabela):
        assert (
            tabela.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert not tabela.horizontalScrollBar().isVisible()

    # 2) a visão "Nova venda" não tem QScrollArea (sem rolagem aninhada).
    assert pagina._vista_venda.findChildren(QScrollArea) == []

    # 3) o botão principal fica inteiro dentro da janela.
    botao = pagina._btn_salvar
    assert botao.isVisible()
    canto = botao.mapTo(principal, QPoint(0, 0))
    assert canto.x() >= 0 and canto.y() >= 0
    assert canto.x() + botao.width() <= principal.width()
    assert canto.y() + botao.height() <= principal.height()

    # 4) rótulos e controles não são cortados na vertical.
    for controle in pagina._vista_venda.findChildren(QPushButton) + pagina._vista_venda.findChildren(
        QComboBox
    ):
        if controle.isHidden():
            continue
        assert controle.height() + 1 >= controle.sizeHint().height(), (
            f"controle cortado: {controle!r} ({largura}x{altura})"
        )

    # 5) os rótulos dos campos condicionais existem acima dos respectivos campos.
    assert not pagina._campo_cliente.isHidden()
    assert not pagina._campo_forma.isHidden()
    assert pagina._lbl_total.isVisible()


@pytest.mark.parametrize("largura,altura", _RESOLUCOES)
def test_grade_de_itens_cabe_na_largura(app, pumpar, largura, altura):
    principal, pagina = _pdv(pumpar)
    principal.resize(largura, altura)
    principal.show()
    app.processEvents()

    editor = pagina._itens_editor
    editor._entrada.setText("B015")
    editor._adicionar_pela_busca()
    app.processEvents()

    # A soma das larguras das colunas visíveis não ultrapassa o viewport.
    tabela = editor._tabela
    colunas = sum(
        tabela.columnWidth(c)
        for c in range(tabela.columnCount())
        if not tabela.isColumnHidden(c)
    )
    assert colunas <= tabela.viewport().width() + 2, (
        f"colunas {colunas} > viewport {tabela.viewport().width()} ({largura}x{altura})"
    )


@pytest.mark.parametrize("largura,altura", _RESOLUCOES)
def test_historico_cabe_na_largura(app, pumpar, largura, altura):
    principal, pagina = _pdv(pumpar)
    principal.resize(largura, altura)
    principal.show()
    app.processEvents()

    pagina._ir_para_historico()
    app.processEvents()

    tabela = pagina._tabela
    assert tabela.rowCount() >= 1
    colunas = sum(
        tabela.columnWidth(c)
        for c in range(tabela.columnCount())
        if not tabela.isColumnHidden(c)
    )
    assert colunas <= tabela.viewport().width() + 2, (
        f"colunas {colunas} > viewport {tabela.viewport().width()} ({largura}x{altura})"
    )
