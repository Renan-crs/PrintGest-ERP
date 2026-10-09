"""Testes da página Cadastro de Clientes (mockup 2.1) contra um daemon fictício."""

from __future__ import annotations

import httpx
import pytest

from printgest.core.api import Api
from printgest.ui.modulos.clientes import PaginaClientes

_CLIENTES = [
    {
        "id": 1,
        "nome_razao": "Agência Criativa SP",
        "tipo_pessoa": "pj",
        "cpf_cnpj": "18.234.901/0001-44",
        "celular": "(11) 98822-1100",
        "email": "oi@criativa.sp",
        "cidade": "São Paulo",
        "uf": "SP",
    },
    {
        "id": 2,
        "nome_razao": "Mariana Alencar",
        "tipo_pessoa": "pf",
        "cpf_cnpj": "322.901.848-12",
        "telefone": "(11) 99402-9988",
        "cidade": "Osasco",
        "uf": "SP",
    },
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, dict]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/clientes":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _CLIENTES, "meta": {"total": len(_CLIENTES), "limit": 50, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/clientes":
        corpo = request.read().decode()
        _ESCRITAS.append(("POST", "", corpo))
        return httpx.Response(200, json={"data": {"id": 3, "nome_razao": "Novo"}})
    if request.method == "PUT" and request.url.path == "/v1/clientes/1":
        _ESCRITAS.append(("PUT", "1", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "nome_razao": "Alterado"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


@pytest.fixture
def pagina():
    _GETS.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaClientes(api)


def test_carrega_grade_e_contador(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._total == 2
    assert "2" in pagina._contador.text()
    assert pagina._tabela.item(0, 2).text() == "Agência Criativa SP"


def test_selecionar_linha_preenche_formulario(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: "Editando" in pagina._form_titulo.text())
    assert pagina._editando_id == 1
    assert pagina._nome.valor() == "Agência Criativa SP"
    assert pagina._tipo.valor() == "pj"
    assert pagina._doc.valor() == "18.234.901/0001-44"


def test_salvar_existente_envia_put_e_recarrega(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._nome.definir("Agencia Criativa SP Ltda")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "PUT" for escr in _ESCRITAS))
    pumpar(lambda: len(_GETS) >= 2)

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PUT", "1")
    import json

    enviado = json.loads(corpo)
    assert enviado["nome_razao"] == "Agencia Criativa SP Ltda"
    assert enviado["tipo_pessoa"] == "pj"
    assert enviado["cep"] is None
    assert len(_GETS) >= 2


def test_botao_novo_limpa_formulario(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert "Novo Cliente" in pagina._form_titulo.text()
    assert pagina._nome.valor() == ""


def test_modo_leitura_desabilita_escrita(app, pumpar):
    _GETS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaClientes(api, modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_novo.isEnabled() is False
    assert pagina._btn_salvar.isEnabled() is False
    assert pagina._nome.widget.isEnabled() is False


def test_busca_dispara_recarga_com_q(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    antes = len(_GETS)
    pagina._busca._publicar()  # simula fim do debounce com o texto atual
    pumpar(lambda: len(_GETS) > antes)
    assert "q" in _GETS[-1].url.params