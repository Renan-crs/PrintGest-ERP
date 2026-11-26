"""Botão Excluir nas telas de cadastro (soft delete) e no estoque."""

from __future__ import annotations

import httpx

from printgest.core.api import Api
from printgest.ui.formulario import CampoTexto
from printgest.ui.modulos.estoque import PaginaEstoqueBase
from printgest.ui.modulos.pagina_crud import PaginaCrud

_CHAMADAS: list[tuple[str, str]] = []


class _Pagina(PaginaCrud):
    ENTIDADE = "clientes"
    CHAVES = ["id", "nome_razao"]
    COLUNAS = ["Nº", "Nome"]
    PESOS = [1, 4]
    CAMPO_NOME = "nome_razao"

    def _secoes(self):
        return [("", [CampoTexto("Nome")])]

    def _payload(self):
        return {"nome_razao": "Ana"}


def _api():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": 3, "nome_razao": "Ana"}],
                    "meta": {"total": 1, "limit": 50, "offset": 0},
                },
            )
        if request.method == "DELETE":
            _CHAMADAS.append((request.method, request.url.path))
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "rota não esperada"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return api


def _pagina():
    _CHAMADAS.clear()
    return _Pagina(_api())


def test_botao_excluir_existe_e_nasce_desabilitado(app):
    pagina = _pagina()
    botao = pagina._btn_excluir
    assert botao.text() == "Excluir"
    assert botao.objectName() == "btnExcluir"
    assert botao.toolTip()
    assert botao.accessibleName() == "Excluir registro"
    assert not botao.isEnabled()


def test_botao_habilita_com_selecao(app):
    pagina = _pagina()
    pagina._tabela.selectRow(0)
    assert pagina._btn_excluir.isEnabled()
    pagina._limpar_form()
    assert not pagina._btn_excluir.isEnabled()


def test_excluir_confirmado_chama_delete(app, monkeypatch):
    from printgest.ui.modulos import pagina_crud as modulo

    pagina = _pagina()
    pagina._tabela.selectRow(0)
    monkeypatch.setattr(
        modulo.QMessageBox,
        "question",
        lambda *_a, **_k: modulo.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(modulo.QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(
        modulo.tarefas, "rodar", lambda fn, on_ok, on_erro: on_ok(fn())
    )

    pagina._excluir()

    assert _CHAMADAS == [("DELETE", "/v1/clientes/3")]


def test_excluir_sem_confirmacao_nao_chama_delete(app, monkeypatch):
    from printgest.ui.modulos import pagina_crud as modulo

    pagina = _pagina()
    pagina._tabela.selectRow(0)
    monkeypatch.setattr(
        modulo.QMessageBox,
        "question",
        lambda *_a, **_k: modulo.QMessageBox.StandardButton.No,
    )
    pagina._excluir()
    assert _CHAMADAS == []


def test_modo_leitura_bloqueia_exclusao(app):
    pagina = _Pagina(_api(), modo_leitura=True)
    assert not pagina._btn_excluir.isEnabled()
    pagina._excluir()
    assert _CHAMADAS == []


def test_estoque_exclui_o_produto_do_catalogo():
    assert PaginaEstoqueBase.ENTIDADE == "estoque"
    assert PaginaEstoqueBase.ENTIDADE_EXCLUIR == "produtos"


def test_linha_de_estoque_usa_produto_id(app, monkeypatch):
    from printgest.ui.modulos import pagina_crud as modulo

    pagina = _pagina()
    pagina.ENTIDADE_EXCLUIR = "produtos"
    pagina._btn_excluir.setEnabled(True)

    class _Tabela:
        def objeto_selecionado(self):
            return {"produto_id": 9, "nome": "Papel"}

        def carregando(self, _valor):
            pass

        def preencher(self, _linhas):
            pass

        def limpar(self):
            pass

    pagina._tabela = _Tabela()
    monkeypatch.setattr(
        modulo.QMessageBox,
        "question",
        lambda *_a, **_k: modulo.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(modulo.QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(
        modulo.tarefas, "rodar", lambda fn, on_ok, on_erro: on_ok(fn())
    )

    pagina._excluir()
    assert _CHAMADAS == [("DELETE", "/v1/produtos/9")]
