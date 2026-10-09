"""Testes de O.S. & Orçamentos (mockups 3.1/3.2/3.3) contra um daemon fictício."""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox, QPushButton

from printgest.core.api import Api
from printgest.ui.modulos.os import PaginaOS, PaginaOrcamento

_OSS = [
    {
        "id": 1,
        "numero": 1044,
        "tipo": "os",
        "status": "aberto",
        "cliente_id": 1,
        "cliente_nome": "Ana",
        "data_previsao_entrega": "2026-09-25",
        "desconto": "0",
        "valor_total": "312.00",
        "forma_pagamento": "pix",
        "itens": [
            {
                "id": 10,
                "seq": 1,
                "produto_id": 5,
                "descricao_avulsa": None,
                "quantidade": "2",
                "dimensoes": "1.20x2.00",
                "valor_unitario": "156.00",
                "desconto": "0",
                "valor_total": "312.00",
                "executado": False,
            }
        ],
    },
    {"id": 2, "numero": 1045, "tipo": "os", "status": "producao", "cliente_id": None, "cliente_nome": "Biz"},
    {"id": 6, "numero": 3100, "tipo": "orcamento", "status": "aberto", "cliente_id": 2, "cliente_nome": "Biz"},
]

_CLIENTES = [{"id": 1, "nome_razao": "Ana"}, {"id": 2, "nome_razao": "Biz"}]
_FUNCIONARIOS = [
    {"id": 10, "nome": "Vina", "e_vendedor": True, "e_atendente": True},
    {"id": 11, "nome": "José", "e_vendedor": False, "e_atendente": True},
]
_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo Frosted 3mm", "preco_venda": "156.00"},
    {"id": 6, "codigo": "B016", "nome": "Banner Lona 440g", "preco_venda": "84.00"},
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/os":
        _GETS.append(request)
        params = request.url.params
        linhas = _OSS
        if params.get("tipo"):
            linhas = [o for o in linhas if o["tipo"] == params["tipo"]]
        if params.get("status"):
            linhas = [o for o in linhas if o["status"] == params["status"]]
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
            200, json={"data": _FUNCIONARIOS, "meta": {"total": 2, "limit": 50, "offset": 0}}
        )
    if request.method == "GET" and request.url.path == "/v1/produtos":
        return httpx.Response(
            200, json={"data": _PRODUTOS, "meta": {"total": 2, "limit": 50, "offset": 0}}
        )
    if request.method == "POST" and request.url.path == "/v1/os":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "numero": 1046}})
    if request.method == "PATCH" and request.url.path == "/v1/os/1/status":
        _ESCRITAS.append(("PATCH", "1/status", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "status": "aprovado"}})
    if request.method == "DELETE" and request.url.path == "/v1/os/1":
        _ESCRITAS.append(("DELETE", "1", ""))
        return httpx.Response(204)
    if request.method == "POST" and request.url.path == "/v1/os/6/converter":
        _ESCRITAS.append(("POST", "6/converter", ""))
        return httpx.Response(200, json={"data": {"id": 7, "numero": 1046}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


@pytest.fixture
def pagina():
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaOS(api)


@pytest.fixture
def pagina_orcamento():
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaOrcamento(api)


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

    monkeypatch.setattr("printgest.ui.modulos.os.QMessageBox", Falso)


def test_carrega_grade_so_de_os(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._total == 2
    assert "2" in pagina._contador.text()
    assert pagina._tabela.item(0, 2).text() == "Ana"
    assert pagina._formatar_texto({"status": "aberto"}, "status") == "ABERTO"


def test_filtro_por_status_vai_ao_daemon(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._btn_filtros["producao"].click()
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    params = _GETS[-1].url.params
    assert params["status"] == "producao"
    assert params["tipo"] == "os"


def test_selecionar_linha_preenche_formulario(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2 and pagina._cliente.widget.count() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    assert pagina._cliente.valor() == 1
    assert pagina._previsao.valor().isoformat() == "2026-09-25"
    assert pagina._forma.valor() == "pix"
    itens = pagina._itens.valor()
    assert len(itens) == 1
    assert itens[0]["produto_id"] == 5
    assert itens[0]["quantidade"] == "2"


def test_nova_os_posta_com_itens_e_cliente(app, pumpar, pagina):
    pumpar(
        lambda: pagina._tabela.rowCount() == 2
        and pagina._cliente.widget.count() == 2
        and pagina._itens._combo_produto.count() > 1
    )
    pagina._btn_novo.click()
    pagina._cliente.definir(1)
    pagina._forma.definir("pix")
    pagina._previsao.definir("2026-09-28")

    combo = pagina._itens._combo_produto
    combo.setCurrentIndex(combo.findData(5))
    pagina._itens._qtd.setText("3")
    pagina._itens._unit.setText("10")
    pagina._itens._dimensoes.setText("1.00x2.00")
    [b for b in pagina._itens.findChildren(QPushButton) if b.text() == "Adicionar"][0].click()
    pumpar(lambda: len(pagina._itens.valor()) == 1)

    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" and escr[1] == "" for escr in _ESCRITAS))

    metodo, _item, corpo = _ESCRITAS[-1]
    assert metodo == "POST"
    enviado = json.loads(corpo)
    assert enviado["tipo"] == "os"
    assert enviado["cliente_id"] == 1
    assert enviado["forma_pagamento"] == "pix"
    assert enviado["data_previsao_entrega"] == "2026-09-28"
    assert enviado["desconto"] == "0"
    item = enviado["itens"][0]
    assert item["produto_id"] == 5
    assert item["quantidade"] == "3"
    assert item["valor_unitario"] == "10"
    assert item["dimensoes"] == "1.00x2.00"


def test_avancar_status_patcha_o_status(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._btn_avancar.click()
    pumpar(lambda: any(escr[0] == "PATCH" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PATCH", "1/status")
    assert json.loads(corpo) == {"status": "aprovado"}


def test_cancelar_os_exclui_registro(app, pumpar, pagina, monkeypatch):
    _sem_dialogos(monkeypatch)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._btn_cancelar_os.click()
    pumpar(lambda: any(escr[0] == "DELETE" for escr in _ESCRITAS))
    assert _ESCRITAS[-1][1] == "1"


def test_modo_leitura_bloqueia_tudo(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaOS(api, modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_salvar.isEnabled() is False
    assert pagina._btn_avancar.isEnabled() is False
    assert pagina._itens._qtd.isEnabled() is False


def test_orcamento_converte_em_os(app, pumpar, pagina_orcamento, monkeypatch):
    _sem_dialogos(monkeypatch)
    pumpar(lambda: pagina_orcamento._tabela.rowCount() == 1)
    pagina_orcamento._tabela.selectRow(0)
    pumpar(lambda: pagina_orcamento._editando_id == 6)
    antes_get = len(_GETS)
    pagina_orcamento._btn_converter.click()
    pumpar(lambda: any(escr[1] == "6/converter" for escr in _ESCRITAS))
    # garante que o on_ok (_convertido, com dialog) rodou ainda dentro do teste,
    # antes do monkeypatch ser revertido — evita modal real no teste seguinte.
    pumpar(lambda: len(_GETS) > antes_get)
    assert _ESCRITAS[-1][0] == "POST"


def test_orcamento_envia_tipo_orcamento_no_post(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaOrcamento(api)
    pumpar(
        lambda: pagina._tabela.rowCount() == 1
        and pagina._cliente.widget.count() == 2
        and pagina._itens._combo_produto.count() > 1
    )
    pagina._btn_novo.click()
    pagina._cliente.definir(2)
    combo = pagina._itens._combo_produto
    combo.setCurrentIndex(combo.findData(6))
    pagina._itens._qtd.setText("1")
    pagina._itens._unit.setText("84")
    [b for b in pagina._itens.findChildren(QPushButton) if b.text() == "Adicionar"][0].click()
    pumpar(lambda: len(pagina._itens.valor()) == 1)
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))
    corpo = json.loads(_ESCRITAS[-1][2])
    assert corpo["tipo"] == "orcamento"