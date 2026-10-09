"""Testes do PDV / Venda de Balcão (mockup 3.4) contra um daemon fictício."""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton

from printgest.core.api import Api
from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao

_VENDAS = [
    {
        "id": 10,
        "numero": 2894,
        "status": "ok",
        "cliente_id": None,
        "cliente_nome": None,
        "vendedor_id": None,
        "forma_pagamento": "pix",
        "parcelas": 1,
        "data_venda": "2026-09-23",
        "desconto": "0",
        "valor_itens": "100.00",
        "valor_total": "100.00",
        "itens": [
            {
                "id": 1,
                "seq": 1,
                "produto_id": 5,
                "descricao_avulsa": None,
                "quantidade": "1",
                "valor_unitario": "100.00",
                "desconto": "0",
                "valor_total": "100.00",
            }
        ],
    }
]

_CLIENTES = [{"id": 1, "nome_razao": "Ana"}, {"id": 2, "nome_razao": "Biz"}]
_FUNCIONARIOS = [{"id": 10, "nome": "Vina", "e_vendedor": True, "e_atendente": False}]
_PRODUTOS = [{"id": 5, "codigo": "B015", "nome": "Adesivo Frosted 3mm", "preco_venda": "100.00"}]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/vendas":
        _GETS.append(request)
        status = request.url.params.get("status_venda")
        linhas = _VENDAS if not status else [v for v in _VENDAS if v["status"] == status]
        return httpx.Response(
            200,
            json={"data": linhas, "meta": {"total": len(linhas), "limit": 50, "offset": 0}},
        )
    if request.method == "GET" and request.url.path == "/v1/clientes":
        return httpx.Response(
            200, json={"data": _CLIENTES, "meta": {"total": 2, "limit": 50, "offset": 0}}
        )
    if request.method == "GET" and request.url.path == "/v1/funcionarios":
        return httpx.Response(
            200, json={"data": _FUNCIONARIOS, "meta": {"total": 1, "limit": 50, "offset": 0}}
        )
    if request.method == "GET" and request.url.path == "/v1/produtos":
        return httpx.Response(
            200, json={"data": _PRODUTOS, "meta": {"total": 1, "limit": 50, "offset": 0}}
        )
    if request.method == "POST" and request.url.path == "/v1/vendas":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 11, "numero": 2895}})
    if request.method == "DELETE" and request.url.path == "/v1/vendas/10":
        _ESCRITAS.append(("DELETE", "10", ""))
        return httpx.Response(204)
    return httpx.Response(404, json={"detail": "rota não esperada"})


@pytest.fixture
def pagina():
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaVendaBalcao(api)


def _sem_dialogos(monkeypatch):
    class Falso:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def question(*_a, **_k):
            return QMessageBox.StandardButton.Yes

        @staticmethod
        def information(*_a, **_k):
            return None

        @staticmethod
        def warning(*_a, **_k):
            return None

        @staticmethod
        def critical(*_a, **_k):
            return None

    monkeypatch.setattr("printgest.ui.modulos.venda_balcao.QMessageBox", Falso)


def test_carrega_grade_e_contador(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert "1" in pagina._contador.text()
    assert pagina._formatar_texto({"status": "ok"}, "status") == "OK"


def test_filtro_canceladas_vai_ao_daemon(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._btn_filtros["cancelado"].click()
    pumpar(lambda: len(_GETS) >= 2)
    assert _GETS[-1].url.params["status_venda"] == "cancelado"


def test_selecionar_venda_preenche_cupom(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 10)
    assert pagina._forma.valor() == "pix"
    assert pagina._parcelas.valor() == "1"
    itens = pagina._itens.valor()
    assert len(itens) == 1
    assert itens[0]["produto_id"] == 5


def test_finalizar_venda_posta_apenas(app, pumpar, pagina):
    pumpar(
        lambda: pagina._tabela.rowCount() == 1
        and pagina._itens._combo_produto.count() > 1
    )
    pagina._btn_novo.click()
    pagina._forma.definir("cartao_debito")
    pagina._parcelas.definir("2")

    combo = pagina._itens._combo_produto
    combo.setCurrentIndex(combo.findData(5))
    pagina._itens._qtd.setText("2")
    pagina._itens._unit.setText("50")
    [b for b in pagina._itens.findChildren(QPushButton) if b.text() == "Adicionar"][0].click()
    pumpar(lambda: len(pagina._itens.valor()) == 1)

    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, _item, corpo = _ESCRITAS[-1]
    assert metodo == "POST"
    enviado = json.loads(corpo)
    assert enviado["forma_pagamento"] == "cartao_debito"
    assert enviado["parcelas"] == 2
    assert enviado["cliente_id"] is None
    assert len(enviado["itens"]) == 1
    assert enviado["itens"][0]["quantidade"] == "2"


def test_cancelar_venda_exclui_registro(app, pumpar, pagina, monkeypatch):
    _sem_dialogos(monkeypatch)
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 10)
    pagina._btn_cancelar_venda.click()
    pumpar(lambda: any(escr[0] == "DELETE" for escr in _ESCRITAS))
    assert _ESCRITAS[-1][1] == "10"


def test_modo_leitura_bloqueia_finalizacao(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaVendaBalcao(api, modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert pagina._btn_salvar.isEnabled() is False
    assert pagina._btn_cancelar_venda.isEnabled() is False
    assert pagina._itens._qtd.isEnabled() is False
    pagina._btn_salvar.click()
    pumpar(lambda: len(_GETS) >= 1)
    assert _ESCRITAS == []