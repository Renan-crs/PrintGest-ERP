"""Testes da página Cadastro de Fornecedores (mockup 2.3) contra daemon fictício."""

from __future__ import annotations

import json

import httpx

from printgest.core.api import Api
from printgest.ui.modulos.fornecedores import PaginaFornecedores

_FORNECEDORES = [
    {
        "id": 1,
        "nome_razao": "Suzano Papel & Celulose Distribuidora",
        "tipo_pessoa": "pj",
        "cpf_cnpj": "16.404.287/0001-55",
        "contato_nome": "Maurício Duarte",
        "celular": "(11) 98844-3321",
        "cidade": "São Paulo",
        "uf": "SP",
    },
    {
        "id": 2,
        "nome_razao": "Serilon Comunicação Visual & Lonas",
        "tipo_pessoa": "pj",
        "cpf_cnpj": "79.231.849/0004-90",
        "contato_nome": "Camila Vasconcellos",
        "telefone": "(41) 99112-7080",
        "cidade": "Curitiba",
        "uf": "PR",
    },
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/fornecedores":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _FORNECEDORES, "meta": {"total": len(_FORNECEDORES), "limit": 50, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/fornecedores":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "nome_razao": "Novo"}})
    if request.method == "PUT" and request.url.path == "/v1/fornecedores/1":
        _ESCRITAS.append(("PUT", "1", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "nome_razao": "Alterado"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaFornecedores(api, modo_leitura=modo_leitura)


def test_carrega_grade_e_contador(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._total == 2
    assert "2" in pagina._contador.text()
    assert pagina._tabela.item(0, 1).text() == "Suzano Papel & Celulose Distribuidora"
    assert pagina._tabela.item(0, 3).text() == "São Paulo/SP"


def test_selecionar_linha_preenche_formulario(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(1)
    pumpar(lambda: pagina._editando_id == 2)
    assert "Editando" in pagina._form_titulo.text()
    assert pagina._nome.valor() == "Serilon Comunicação Visual & Lonas"
    assert pagina._representante.valor() == "Camila Vasconcellos"
    assert pagina._tipo.valor() == "pj"


def test_salvar_existente_envia_put(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._representante.definir("Maurício Duarte Jr")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "PUT" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PUT", "1")
    enviado = json.loads(corpo)
    assert enviado["nome_razao"] == "Suzano Papel & Celulose Distribuidora"
    assert enviado["contato_nome"] == "Maurício Duarte Jr"
    assert enviado["tipo_pessoa"] == "pj"


def test_criar_novo_envia_post_e_padroes(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert pagina._tipo.valor() == "pj"
    pagina._nome.definir("Papelaria Andrade")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("POST", "")
    enviado = json.loads(corpo)
    assert enviado["nome_razao"] == "Papelaria Andrade"
    assert enviado["tipo_pessoa"] == "pj"
    assert enviado["cep"] is None


def test_modo_leitura_nao_salva(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina(modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_novo.isEnabled() is False
    assert pagina._btn_salvar.isEnabled() is False
    pagina._btn_salvar.click()
    assert _ESCRITAS == []