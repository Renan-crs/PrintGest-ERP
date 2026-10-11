"""Testes do módulo Estoque (mockups 4.1–4.3) contra um daemon fictício."""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox

from printgest.core.api import Api
from printgest.ui.modulos.estoque import (
    PaginaEstoqueConsulta,
    PaginaEstoqueMovimento,
    PaginaEstoqueReposicao,
)

_LINHAS = [
    {
        "produto_id": 7,
        "codigo": "INS-0209",
        "nome": "Adesivo Vinil Fosco 0.10mm",
        "categoria_id": 1,
        "categoria_nome": "Bobinas & Mídias",
        "unidade": "m",
        "dimensoes": "1.26x50m",
        "e_bobina": True,
        "preco_custo": "3.60",
        "preco_venda": "9.90",
        "estoque_minimo": "4",
        "saldo": "2.5",
        "reservado": "0",
        "disponivel": "2.5",
        "valor_estoque": "9.00",
        "status": "critico",
        "ativo": True,
    },
    {
        "produto_id": 8,
        "codigo": "PAP-0104",
        "nome": "Papel Couché 115g SRA3",
        "categoria_id": 2,
        "categoria_nome": "Papéis & Cartões",
        "unidade": "resma",
        "dimensoes": None,
        "e_bobina": False,
        "preco_custo": "12.50",
        "preco_venda": "25.90",
        "estoque_minimo": "5",
        "saldo": "30",
        "reservado": "0",
        "disponivel": "30",
        "valor_estoque": "375.00",
        "status": "normal",
        "ativo": True,
    },
]

_RESUMO = {
    "total_itens": 842,
    "itens_ativos": 830,
    "valor_total": "148920.45",
    "total_bobinas": 38,
    "abaixo_minimo": 12,
}

_KARDEX = [
    {
        "id": 1,
        "produto_id": 7,
        "tipo": "saida",
        "origem": "ajuste_manual",
        "documento_id": None,
        "quantidade": "-15",
        "saldo_anterior": "17.5",
        "saldo_posterior": "2.5",
        "custo_unitario": "3.60",
        "motivo": "Perda na calibragem da Roland SG3",
        "operador_nome": "Roberto Silva",
        "criado_em": "2026-09-23T10:14:00",
    }
]

_REPOSICAO = [
    {
        "produto_id": 7,
        "codigo": "INS-0209",
        "nome": "Adesivo Vinil Fosco 0.10mm",
        "categoria_nome": "Bobinas & Mídias",
        "fornecedor_nome": None,
        "saldo": "2.5",
        "estoque_minimo": "4",
        "giro_diario": "0.8",
        "autonomia_dias": "3.1",
        "sugestao": "6",
        "custo_est": "21.60",
        "status": "critico",
    }
]

_GETS_ESTOQUE: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/estoque":
        _GETS_ESTOQUE.append(request)
        abaixo = request.url.params.get("abaixo_minimo") == "true"
        linhas = [r for r in _LINHAS if r["status"] == "critico"] if abaixo else _LINHAS
        return httpx.Response(
            200,
            json={"data": linhas, "meta": {"total": len(linhas), "limit": 50, "offset": 0}},
        )
    if request.method == "GET" and request.url.path == "/v1/estoque/resumo":
        _GETS_ESTOQUE.append(request)
        return httpx.Response(200, json={"data": _RESUMO})
    if request.method == "GET" and request.url.path == "/v1/estoque/reposicao":
        _GETS_ESTOQUE.append(request)
        return httpx.Response(
            200,
            json={"data": _REPOSICAO, "meta": {"total": 1, "limit": 100, "offset": 0}},
        )
    if request.method == "GET" and request.url.path == f"/v1/estoque/{_LINHAS[0]['produto_id']}/kardex":
        _GETS_ESTOQUE.append(request)
        return httpx.Response(
            200, json={"data": _KARDEX, "meta": {"total": 1, "limit": 200, "offset": 0}}
        )
    if request.method == "POST" and request.url.path == "/v1/estoque/movimentar":
        _ESCRITAS.append(("POST", request.read().decode()))
        return httpx.Response(
            200,
            json={
                "data": {
                    "movimento": {
                        "id": 2,
                        "produto_id": 7,
                        "tipo": "saida",
                        "origem": "ajuste_manual",
                        "quantidade": "-1",
                        "saldo_anterior": "2.5",
                        "saldo_posterior": "1.5",
                    },
                    "saldo": "2.0",
                }
            },
        )
    return httpx.Response(404, json={"detail": "rota não esperada: " + request.url.path})


def _api():
    _GETS_ESTOQUE.clear()
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana"}})
    return api


def _sem_dialogos(monkeypatch):
    class Falso:
        @staticmethod
        def warning(*_a, **_k):
            return None

        @staticmethod
        def critical(*_a, **_k):
            return None

        @staticmethod
        def information(*_a, **_k):
            return None

    monkeypatch.setattr("printgest.ui.modulos.estoque.QMessageBox", Falso)


def test_consulta_carrega_grade_filtra_e_kpis(app, pumpar):
    pagina = PaginaEstoqueConsulta(_api())
    pumpar(
        lambda: pagina._tabela.rowCount() == 2
        and not pagina._badges_kpi["itens"].text().endswith("–")
    )
    assert "de 2 registros" in pagina._paginador._info.text()
    assert pagina._badges_kpi["itens"].text() == "Itens: 842"
    assert "R$ 148.920,45" in pagina._badges_kpi["valor"].text()
    assert pagina._badges_kpi["bobinas"].text() == "Bobinas: 38"
    assert pagina._badges_kpi["abaixo"].text() == "Abaixo mín.: 12"

    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._produto_atual is not None)
    assert pagina._f_codigo.valor() == "INS-0209"
    assert str(pagina._f_saldo.valor()) == "2.5"
    assert "INS-0209" in pagina._form_titulo.text()

    pagina._btn_filtros["abaixo"].click()
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert any(
        r.url.params.get("abaixo_minimo") == "true" for r in _GETS_ESTOQUE
    )


def test_consulta_formata_colunas(app):
    pagina = PaginaEstoqueConsulta(_api())
    assert pagina._formatar_texto(
        {"status": "critico", "preco_custo": "3.6", "valor_estoque": "9.00"}, "status"
    ) == "CRÍTICO (repor)"
    assert pagina._formatar_texto(
        {"preco_custo": "3.6", "valor_estoque": "9.00"}, "preco_custo"
    ) == "R$ 3,60"


def test_movimento_lanca_saida_com_saldo_projetado(app, pumpar):
    pagina = PaginaEstoqueMovimento(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._produto_atual is not None)
    assert "2.5 → 2.5" in pagina._f_saldo.valor()

    pagina._tipo.definir("saida")
    pagina._quantidade.definir("1")
    pumpar(lambda: "1.5" in pagina._f_saldo.valor())
    pagina._motivo.definir("Perda na calibragem")

    pagina._btn_salvar.click()
    pumpar(lambda: pagina._ultima_movimentacao is not None)

    metodo, corpo = _ESCRITAS[-1]
    assert metodo == "POST"
    enviado = json.loads(corpo)
    assert enviado["produto_id"] == 7
    assert enviado["tipo"] == "saida"
    assert enviado["quantidade"] == "1"
    assert enviado["motivo"] == "Perda na calibragem"


def test_movimento_valida_sem_selecao(app, pumpar, monkeypatch):
    _sem_dialogos(monkeypatch)
    pagina = PaginaEstoqueMovimento(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._btn_salvar.click()
    pumpar(lambda: True)
    assert _ESCRITAS == []
    assert pagina._ultima_movimentacao is None


def test_kardex_abre_dialogo(app, pumpar):
    pagina = PaginaEstoqueConsulta(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._produto_atual is not None)
    pagina._btn_kardex.click()
    pumpar(lambda: pagina._kardex_tabela.rowCount() == 1)
    assert pagina._ultimo_dialogo_kardex.windowTitle().startswith("Ficha Kardex")
    assert pagina._kardex_tabela.item(0, 1).text() == "SAIDA"


def test_reposicao_carrega_badges_e_selecao(app, pumpar):
    pagina = PaginaEstoqueReposicao(_api())
    pumpar(
        lambda: pagina._tabela.rowCount() == 1
        and not pagina._badge_itens.text().endswith("–")
    )
    assert pagina._badge_itens.text() == "Itens: 1"
    assert "R$ 21,60" in pagina._badge_valor.text()

    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._produto_atual is not None)
    assert pagina._f_autonomia.valor() == "3.1 dias"
    assert str(pagina._f_sugestao.valor()) == "6"
    assert "INS-0209" in pagina._form_titulo.text()


def test_reposicao_define_produto_para_emitir_pedido(app, pumpar, monkeypatch):
    _sem_dialogos(monkeypatch)
    pagina = PaginaEstoqueReposicao(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._produto_atual is not None)
    assert pagina._produto_atual["produto_id"] == 7