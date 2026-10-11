"""Testes do PDV / Venda de Balcão (duas visões) contra um daemon fictício."""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QLabel, QMessageBox

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

_CLIENTES = [
    {"id": 1, "nome_razao": "Ana"},
    {"id": 2, "nome_razao": "Biz", "sinal": True, "sinal_pct": "50"},
]
_FUNCIONARIOS = [{"id": 10, "nome": "Vina", "e_vendedor": True, "e_atendente": False}]
_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo Frosted 3mm", "preco_venda": "100.00"}
]

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


def _api() -> Api:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return api


@pytest.fixture
def pagina():
    _GETS.clear()
    _ESCRITAS.clear()
    return PaginaVendaBalcao(_api())


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


def _adicionar_item(pagina, codigo="B015"):
    pagina._itens_editor._entrada.setText(codigo)
    pagina._itens_editor._adicionar_pela_busca()


# --- Visões e histórico ---------------------------------------------------------


def test_abre_na_visao_nova_venda(app, pagina):
    assert pagina._vistas.currentIndex() == 0
    assert pagina._botao_venda.isChecked() is True
    assert pagina._botao_historico.isChecked() is False


def test_visao_historico_carrega_lista(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._ir_para_historico()
    assert pagina._vistas.currentIndex() == 1
    assert pagina._paginador._info.text().startswith("Exibindo 1–1 de 1")
    assert pagina._btn_exportar.isEnabled() is True


def test_estado_vazio_da_lista(app, pumpar):
    def _vazio(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/vendas":
            return httpx.Response(
                200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
            )
        return httpx.Response(404, json={})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaVendaBalcao(api)
    pumpar(lambda: pagina._total == 0 and pagina._pilha_lista.currentWidget() is pagina._vazio)
    assert "Nenhuma venda" in pagina._vazio.text()
    assert pagina._btn_exportar.isEnabled() is False
    # C1: a contagem vive só no rodapé, não há badge no topo.
    assert not hasattr(pagina, "_contador")


def test_filtro_finalizadas_vai_ao_daemon(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._btn_filtros["ok"].click()
    pumpar(lambda: len(_GETS) >= 2)
    assert _GETS[-1].url.params["status_venda"] == "ok"
    assert pagina._btn_filtros["ok"].isChecked() is True


def test_historico_usa_ctrl_f_sem_conflito_com_f2(app, pagina):
    # C3: a busca local usa Ctrl+F (F2 é global para Clientes) e não exibe chip.
    from PySide6.QtGui import QKeySequence

    assert pagina._busca._atalho.key() == QKeySequence("Ctrl+F")
    assert pagina._busca._atalho.key() != QKeySequence("F2")


# --- Nova venda: itens e totais ------------------------------------------------


def test_busca_de_produto_adiciona_item(app, pumpar, pagina):
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    itens = pagina._itens_editor.valor()
    assert len(itens) == 1
    assert itens[0]["produto_id"] == 5
    assert itens[0]["valor_unitario"] == "100.00"
    assert pagina._lbl_total.text() == "R$ 100,00"


def test_totais_consideram_quantidade_e_desconto(app, pumpar, pagina):
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)  # 1 × 100
    pagina._itens_editor._itens[0]["quantidade"] = "3"
    pagina._itens_editor._atualizar()  # 300
    assert pagina._lbl_total.text() == "R$ 300,00"

    pagina._desconto.definir("50")  # 250
    assert pagina._lbl_total.text() == "R$ 250,00"


def test_valor_grande_usa_separador_de_milhar(app, pumpar, pagina):
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    pagina._itens_editor._itens[0]["valor_unitario"] = "123456.78"
    pagina._itens_editor._atualizar()
    assert pagina._lbl_total.text() == "R$ 123.456,78"


def test_campos_condicionais_por_forma_de_pagamento(app, pagina):
    # Padrão: dinheiro → valor recebido/troco visíveis, parcelas oculto.
    assert not pagina._campo_recebido.isHidden()
    assert not pagina._campo_troco.isHidden()
    assert pagina._campo_parcelas.isHidden()

    pagina._forma.definir("cartao_credito")
    assert not pagina._campo_parcelas.isHidden()
    assert pagina._campo_recebido.isHidden()
    assert pagina._campo_troco.isHidden()

    pagina._forma.definir("pix")
    assert pagina._campo_parcelas.isHidden()
    assert pagina._campo_recebido.isHidden()


def test_formulario_limpa_apos_finalizar(app, pumpar, pagina):
    pumpar(
        lambda: "b015" in pagina._itens_editor._por_codigo
        and pagina._cliente.widget.count() == 3
    )
    _adicionar_item(pagina)
    pagina._btn_salvar.click()
    pumpar(lambda: pagina._itens_editor.valor() == [])
    # Formulário limpo após sucesso: sem itens e total zerado.
    assert pagina._itens_editor.valor() == []
    assert pagina._lbl_total.text() == "R$ 0,00"


# --- Finalização ---------------------------------------------------------------


def test_finalizar_venda_posta_apenas(app, pumpar, pagina):
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    pagina._forma.definir("cartao_debito")
    pumpar(lambda: len(pagina._itens_editor.valor()) == 1)

    pagina._btn_salvar.click()
    pumpar(lambda: any(e[0] == "POST" for e in _ESCRITAS))

    enviado = json.loads(_ESCRITAS[-1][2])
    assert enviado["forma_pagamento"] == "cartao_debito"
    assert enviado["parcelas"] == 1  # forma não parcelável força 1
    assert enviado["cliente_id"] is None
    assert len(enviado["itens"]) == 1
    assert enviado["itens"][0]["quantidade"] == "1"
    assert "dimensoes" not in enviado["itens"][0]


def test_modo_leitura_bloqueia_finalizacao(app):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = PaginaVendaBalcao(_api(), modo_leitura=True)
    assert pagina._btn_salvar.isEnabled() is False
    assert pagina._itens_editor._entrada.isEnabled() is False
    pagina._btn_salvar.click()
    assert _ESCRITAS == []


# --- Pagamento antecipado / sinal ----------------------------------------------


def test_venda_exige_confirmacao_para_cliente_com_sinal(app, pumpar, pagina, monkeypatch):
    avisos = []

    class Falso:
        StandardButton = QMessageBox.StandardButton

        @staticmethod
        def warning(*_a, **_k):
            avisos.append(_a[-1] if _a else "")

        @staticmethod
        def information(*_a, **_k):
            return None

        @staticmethod
        def critical(*_a, **_k):
            return None

    monkeypatch.setattr("printgest.ui.modulos.venda_balcao.QMessageBox", Falso)

    pumpar(
        lambda: "b015" in pagina._itens_editor._por_codigo
        and pagina._cliente.widget.count() == 3
    )
    pagina._cliente.definir(2)
    assert "sinal" in pagina._pagamento_confirmado.widget.text().lower()
    _adicionar_item(pagina)
    pumpar(lambda: len(pagina._itens_editor.valor()) == 1)

    pagina._btn_salvar.click()
    assert _ESCRITAS == []
    assert avisos and "sinal" in avisos[0].lower()


def test_venda_confirmada_envia_pagamento_confirmado(app, pumpar, pagina):
    pumpar(
        lambda: "b015" in pagina._itens_editor._por_codigo
        and pagina._cliente.widget.count() == 3
    )
    pagina._cliente.definir(2)
    _adicionar_item(pagina)
    pumpar(lambda: len(pagina._itens_editor.valor()) == 1)

    pagina._pagamento_confirmado.definir(True)
    pagina._btn_salvar.click()
    pumpar(lambda: any(e[0] == "POST" for e in _ESCRITAS))

    enviado = json.loads(_ESCRITAS[-1][2])
    assert enviado["cliente_id"] == 2
    assert enviado["pagamento_confirmado"] is True


# --- Cancelamento e navegação --------------------------------------------------


def test_cancelar_venda_exclui_registro(app, pumpar, pagina, monkeypatch):
    _sem_dialogos(monkeypatch)
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._cancelar_venda(pagina._linhas[0])
    pumpar(lambda: any(e[0] == "DELETE" for e in _ESCRITAS))
    assert _ESCRITAS[-1][1] == "10"


def test_nova_os_emite_navegacao(app):
    pagina = PaginaVendaBalcao(_api(), nivel="operador")
    recebidos: list[str] = []
    pagina.navegar.connect(recebidos.append)
    assert not pagina._btn_nova_os.isHidden()
    pagina._btn_nova_os.click()
    assert recebidos == ["os"]


def test_caixa_nao_ve_nova_os(app):
    pagina = PaginaVendaBalcao(_api(), nivel="caixa")
    assert pagina._btn_nova_os.isHidden()


def test_remover_item_atualiza_grade(app, pumpar, pagina):
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    _adicionar_item(pagina)
    assert pagina._itens_editor._tabela.rowCount() == 2
    pagina._itens_editor._remover_linha(0)
    assert pagina._itens_editor._tabela.rowCount() == 1
    assert len(pagina._itens_editor.valor()) == 1
