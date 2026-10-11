"""Testes da página Cadastro de Categorias."""

from __future__ import annotations

import json

import httpx

from printgest.core.api import Api
from printgest.ui.modulos.categorias import PaginaCategorias

_CATEGORIAS = [
    {"id": 1, "nome": "Papéis & Gramaturas", "description": None},
    {"id": 2, "nome": "Suprimentos", "description": "Toners, tintas e químicos"},
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/categorias":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _CATEGORIAS, "meta": {"total": len(_CATEGORIAS), "limit": 50, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/categorias":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "nome": "Novo"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaCategorias(api, modo_leitura=modo_leitura)


def test_carrega_grade(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._total == 2
    assert pagina._tabela.item(1, 1).text() == "Suprimentos"


def test_selecionar_preenche(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(1)
    pumpar(lambda: pagina._editando_id == 2)
    assert pagina._nome.valor() == "Suprimentos"
    assert pagina._descricao.valor() == "Toners, tintas e químicos"
    assert "#00002" in pagina._form_titulo.text()


def test_criar_nova_envia_post(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert pagina._nome.valor() == ""
    pagina._nome.definir("Fotolito & Filmes")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("POST", "")
    enviado = json.loads(corpo)
    assert enviado["nome"] == "Fotolito & Filmes"
    assert enviado["description"] is None


def test_busca_dispara_recarga(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    antes = len(_GETS)
    pagina._busca._publicar()
    pumpar(lambda: len(_GETS) > antes)
    assert "q" in _GETS[-1].url.params