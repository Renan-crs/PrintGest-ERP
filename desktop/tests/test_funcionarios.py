"""Testes da página Cadastro de Funcionários."""

from __future__ import annotations

import json

import httpx

from printgest.core.api import Api
from printgest.ui.modulos.funcionarios import PaginaFuncionarios

_FUNCIONARIOS = [
    {
        "id": 1,
        "nome": "Marta Souza",
        "login": "marta.souza",
        "cpf": "293.881.440-10",
        "cargo": "Impressão Digital",
        "telefone": "(11) 99311-4455",
        "email": "marta@grafica.local",
        "e_vendedor": False,
        "e_atendente": True,
        "e_producao": True,
        "comissao_pct": "0",
        "data_admissao": "2023-03-01",
    },
    {
        "id": 2,
        "nome": "Carlos Pereira",
        "login": "carlos.pereira",
        "cpf": "155.443.887-90",
        "cargo": "Representante",
        "email": "carlos@grafica.local",
        "e_vendedor": True,
        "e_atendente": True,
        "e_producao": False,
        "comissao_pct": "5.5",
        "data_nascimento": "1988-11-02",
    },
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/funcionarios":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _FUNCIONARIOS, "meta": {"total": len(_FUNCIONARIOS), "limit": 50, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/funcionarios":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "nome": "Novo"}})
    if request.method == "PUT" and request.url.path == "/v1/funcionarios/1":
        _ESCRITAS.append(("PUT", "1", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "nome": "Alterado"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaFuncionarios(api, modo_leitura=modo_leitura)


def test_carrega_grade_e_total(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._total == 2
    assert "de 2 registros" in pagina._paginador._info.text()
    assert pagina._tabela.item(0, 1).text() == "Marta Souza"
    assert pagina._tabela.item(0, 5).text() == "Atend. / Prod."


def test_selecionar_linha_preenche_formulario(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(1)
    pumpar(lambda: pagina._editando_id == 2)
    assert "Editando" in pagina._form_titulo.text()
    assert pagina._nome.valor() == "Carlos Pereira"
    assert pagina._cpf.valor() == "155.443.887-90"
    assert pagina._e_vendedor.valor() is True
    assert pagina._admissao.valor() is None
    assert pagina._comissao.valor() is not None


def test_salvar_existente_envia_put_e_datapara_iso(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._nome.definir("Marta Souza Lopes")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "PUT" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PUT", "1")
    enviado = json.loads(corpo)
    assert enviado["nome"] == "Marta Souza Lopes"
    assert enviado["data_admissao"] == "2023-03-01"
    assert enviado["data_nascimento"] is None
    assert enviado["e_atendente"] is True
    assert enviado["comissao_pct"] == "0"
    # Login é imutável: não deve ser reenviado no PUT.
    assert "login" not in enviado
    assert pagina._login.valor() == "marta.souza"
    assert pagina._login.widget.isEnabled() is False


def test_criar_novo_aplica_padroes_e_envia_post(app, pumpar, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    avisos: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _titulo, texto, *a, **k: avisos.append(texto),
    )
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert pagina._nome.valor() == ""
    assert pagina._comissao.valor() == 0
    assert pagina._login.widget.isEnabled() is True
    pagina._nome.definir("Junia Lima")
    pagina._cargo.definir("Acabamento")
    pagina._comissao.definir("2,5")
    pagina._login.definir("junia.lima")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("POST", "")
    enviado = json.loads(corpo)
    assert enviado["nome"] == "Junia Lima"
    assert enviado["cargo"] == "Acabamento"
    assert enviado["login"] == "junia.lima"
    assert float(enviado["comissao_pct"].replace(",", ".")) == 2.5
    assert enviado["data_nascimento"] is None
    assert enviado["e_vendedor"] is False
    assert avisos and "junia.lima" in avisos[-1]
    assert "primeiro acesso" in avisos[-1].lower()


def test_criar_exige_login_valido(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._btn_novo.click()
    pagina._nome.definir("Sem Login")
    assert pagina._validar() is not None

    pagina._login.definir("ab")  # curto demais
    assert pagina._validar() is not None

    pagina._login.definir("sem login")
    assert pagina._validar() is not None

    pagina._login.definir("sem_login")
    assert pagina._validar() is None


def test_modo_leitura_nao_salva(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina(modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_salvar.isEnabled() is False
    pagina._btn_salvar.click()
    assert _ESCRITAS == []