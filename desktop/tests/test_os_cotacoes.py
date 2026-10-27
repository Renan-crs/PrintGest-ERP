"""Testes da UI do orçamento com item de fornecedor e cotações (M1, §3.2.2)."""

from __future__ import annotations

import httpx
from PySide6.QtWidgets import QMessageBox, QPushButton

from printgest.core.api import Api
from printgest.ui.grade_itens import GradeItens
from printgest.ui.modulos.os import DialogoCotacoes, PaginaOrcamento

_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo", "preco_venda": "10.00"},
]
_FORNECEDORES = [
    {"id": 3, "nome_razao": "Laminadora", "tipo_pessoa": "pj"},
]
_COTACOES = [
    {"id": 1, "fornecedor_id": 3, "fornecedor_nome": "Laminadora",
     "vf": "87.35", "prazo_dias": 5, "selecionada": True,
     "criado_em": "2026-10-27T10:00:00"},
]


def _handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p.startswith("/v1/produtos"):
        return httpx.Response(200, json={"data": _PRODUTOS, "meta": {"total": 1, "limit": 50, "offset": 0}})
    if p.startswith("/v1/fornecedores"):
        return httpx.Response(200, json={"data": _FORNECEDORES, "meta": {"total": 1, "limit": 50, "offset": 0}})
    if p.startswith("/v1/funcionarios"):
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if p.startswith("/v1/clientes"):
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if p == "/v1/os" and request.method == "GET":
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if "/cotacoes" in p:
        return httpx.Response(200, json={
            "data": _COTACOES,
            "estado_cotacao": "cotado",
            "selecionado": {"vf": "87.35", "cp": "200.91", "vo": "212.96",
                            "acrescimo_fornecedor_pct": "130", "markup_orcamento_pct": "6"},
        })
    return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})


def _api():
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "Admin", "login": "admin", "nivel_acesso": "admin"}})
    return api


# ------------------------------------------------------------- GradeItens (tipo)


def test_grade_adiciona_item_de_fornecedor(app):
    grade = GradeItens(api=_api())
    grade._check_fornecedor.setChecked(True)
    grade._descricao.setText("Hot stamping fosco")
    grade._adicionar()
    assert grade._itens[0]["tipo"] == "fornecedor"
    linhas = grade._linhas_display()
    assert "Fornecedor" in linhas[0]["tipo"]
    assert "Aguardando" in linhas[0]["tipo"]  # sem estado_cotacao ainda


def test_grade_proprio_por_padrao(app):
    grade = GradeItens(api=_api())
    grade._descricao.setText("Impressão interna")
    grade._adicionar()
    assert grade._itens[0]["tipo"] == "proprio"
    assert "Próprio" in grade._linhas_display()[0]["tipo"]


def test_grade_definir_le_tipo_e_estado_do_backend(app):
    grade = GradeItens(api=_api())
    grade.definir([
        {"id": 10, "tipo": "fornecedor", "estado_cotacao": "cotado",
         "descricao_avulsa": "Hot stamping", "quantidade": "1",
         "valor_unitario": "212.96", "desconto": "0"},
    ])
    assert grade._itens[0]["tipo"] == "fornecedor"
    assert grade._itens[0]["estado_cotacao"] == "cotado"
    assert "Cotado" in grade._linhas_display()[0]["tipo"]


def test_grade_item_selecionado_devolve_dados_internos(app):
    grade = GradeItens(api=_api())
    grade.definir([
        {"id": 10, "tipo": "fornecedor", "descricao_avulsa": "Hot stamping",
         "quantidade": "1", "valor_unitario": "0", "desconto": "0"},
        {"id": 11, "tipo": "proprio", "descricao_avulsa": "Impressão",
         "quantidade": "2", "valor_unitario": "5", "desconto": "0"},
    ])
    grade._tabela.selectRow(0)
    item = grade.item_selecionado
    assert item is not None
    assert item["tipo"] == "fornecedor"
    assert item["id"] == 10


def test_grade_payload_inclui_tipo(app):
    grade = GradeItens(api=_api())
    grade._check_fornecedor.setChecked(True)
    grade._descricao.setText("Corte e vinco")
    grade._adicionar()
    payload = grade.valor()
    assert payload[0]["tipo"] == "fornecedor"


# ------------------------------------------------------- Api (rotas de cotacao)


def test_api_cotacoes_rota_correta(app):
    api = _api()
    chamadas: list[str] = []
    original = httpx.MockTransport(_handler)

    def handler_com_registro(request):
        chamadas.append(f"{request.method} {request.url.path}")
        return _handler(request)

    api2 = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_com_registro))
    api2.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    api2.listar_cotacoes(7, 10)
    assert "GET /v1/os/7/itens/10/cotacoes" in chamadas

    api2.lancar_cotacao(7, 10, {"fornecedor_id": 3, "vf": "50.00"})
    assert "POST /v1/os/7/itens/10/cotacoes" in chamadas

    api2.selecionar_cotacao(7, 10, 99)
    assert "PUT /v1/os/7/itens/10/cotacoes/99/selecionar" in chamadas


# ------------------------------------------------------- DialogoCotacoes


def test_dialogo_mostra_vf_e_snapshot_quando_presentes(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "Hot stamping"})
    texto = dialogo.informativeText()
    assert "VF: R$ 87.35" in texto
    assert "CP: R$ 200.91" in texto
    assert "VO: R$ 212.96" in texto
    assert "✓" in texto  # cotação selecionada marcada


def test_dialogo_sem_cotacoes_orienta(app):
    def handler_vazio(request):
        if "/cotacoes" in request.url.path:
            return httpx.Response(200, json={"data": [], "estado_cotacao": "aguardando", "selecionado": None})
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_vazio))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    assert "Nenhuma cotação" in dialogo.informativeText()


def test_dialogo_vf_restrito_para_operador(app):
    """Sem `ver_custo_terceiro`, o servidor omite vf — o diálogo mostra (restrito)."""
    def handler_operador(request):
        if "/cotacoes" in request.url.path:
            return httpx.Response(200, json={
                "data": [{"id": 1, "fornecedor_id": 3, "fornecedor_nome": "Laminadora",
                          "prazo_dias": 5, "selecionada": True,
                          "criado_em": "2026-10-27T10:00:00"}],  # SEM vf
                "estado_cotacao": "cotado",
                "selecionado": None,  # SEM snapshot
            })
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_operador))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    texto = dialogo.informativeText()
    assert "restrito" in texto
    assert "CP:" not in texto  # snapshot não veio
