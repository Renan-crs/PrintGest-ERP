"""Testes da página Cadastro de Produtos & Serviços (mockup 2.2)."""

from __future__ import annotations

import json

import httpx

from printgest.core.api import Api
from printgest.ui.modulos.produtos import PaginaProdutos

_PRODUTOS = [
    {
        "id": 1,
        "codigo": "00001",
        "nome": "Papel A4 75g Resma",
        "tipo": "produto",
        "categoria_id": 2,
        "unidade": "un",
        "preco_venda": "38.50",
        "preco_custo": "22.00",
    },
    {
        "id": 2,
        "codigo": "00002",
        "nome": "Impressão 4x4 (1000 u.)",
        "tipo": "servico",
        "categoria_id": None,
        "unidade": "un",
        "preco_venda": "184.70",
        "preco_custo": "84.70",
    },
]

_CATEGORIAS = [
    {"id": 1, "nome": "Papéis & Gramaturas"},
    {"id": 2, "nome": "Suprimentos"},
    {"id": 3, "nome": "Acabamento"},
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/produtos":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _PRODUTOS, "meta": {"total": len(_PRODUTOS), "limit": 50, "offset": 0}},
        )
    if request.method == "GET" and request.url.path == "/v1/categorias":
        return httpx.Response(
            200,
            json={"data": _CATEGORIAS, "meta": {"total": len(_CATEGORIAS), "limit": 1000, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/produtos":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "nome": "Novo"}})
    if request.method == "PUT" and request.url.path == "/v1/produtos/1":
        _ESCRITAS.append(("PUT", "1", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "nome": "Alterado"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaProdutos(api, modo_leitura=modo_leitura)


def test_carrega_grade_e_categorias(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    assert pagina._contador.text() == "2 registros"
    assert "Papel A4" in pagina._tabela.item(0, 2).text()
    assert pagina._tabela.item(0, 5).text() == "R$ 38,50"
    assert pagina._nomes_cat.get(2) == "Suprimentos"


def test_selecionar_linha_preenche_formulario(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    assert pagina._nome.valor() == "Papel A4 75g Resma"
    assert pagina._codigo.valor() == "00001"
    assert pagina._categoria.valor() == 2
    assert pagina._preco_venda.valor() is not None


def test_criar_novo_aplica_padroes_e_envia_post(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert pagina._tipo.valor() == "produto"
    assert pagina._controla.valor() is True
    assert pagina._unidade.valor() == "un"
    pagina._codigo.definir("00009")
    pagina._nome.definir("Papel Couché 115g")
    pagina._categoria.definir(3)
    pagina._preco_venda.definir("12,90")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("POST", "")
    enviado = json.loads(corpo)
    assert enviado["codigo"] == "00009"
    assert enviado["nome"] == "Papel Couché 115g"
    assert enviado["categoria_id"] == 3
    assert float(enviado["preco_venda"].replace(",", ".")) == 12.9
    assert enviado["controla_estoque"] is True
    assert enviado["tipo"] == "produto"


def test_salvar_existente_envia_put(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._nome.definir("Papel A4 75g Resma (2ª face)")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "PUT" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PUT", "1")
    enviado = json.loads(corpo)
    assert enviado["nome"] == "Papel A4 75g Resma (2ª face)"
    assert enviado["categoria_id"] == 2


def test_modo_leitura_nao_salva(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina(modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_salvar.isEnabled() is False
    pagina._btn_salvar.click()
    assert _ESCRITAS == []