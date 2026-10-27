"""Testes da UI do orçamento com item de fornecedor e cotações (M1, §3.2.2)."""

from __future__ import annotations

import httpx
from PySide6.QtWidgets import QPushButton

from printgest.core.api import Api
from printgest.ui.grade_itens import GradeItens
from printgest.ui.modulos.os import DialogoCotacoes
from printgest.ui.tabela import TabelaDensa

_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo", "preco_venda": "10.00"},
]
_FORNECEDORES = [
    {"id": 3, "nome_razao": "Laminadora", "tipo_pessoa": "pj"},
    {"id": 4, "nome_razao": "Gráfica B", "tipo_pessoa": "pj"},
]
_COTACOES = [
    {"id": 1, "fornecedor_id": 3, "fornecedor_nome": "Laminadora",
     "vf": "87.35", "prazo_dias": 5, "validade": "2026-11-30",
     "selecionada": True, "criado_em": "2026-10-27T10:00:00"},
    {"id": 2, "fornecedor_id": 4, "fornecedor_nome": "Gráfica B",
     "vf": "100.00", "prazo_dias": 3, "validade": None,
     "selecionada": False, "criado_em": "2026-10-27T11:00:00"},
]


def _handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p.startswith("/v1/produtos"):
        return httpx.Response(200, json={"data": _PRODUTOS, "meta": {"total": 1, "limit": 50, "offset": 0}})
    if p.startswith("/v1/fornecedores"):
        return httpx.Response(200, json={"data": _FORNECEDORES, "meta": {"total": 2, "limit": 50, "offset": 0}})
    if p.startswith("/v1/funcionarios"):
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if p.startswith("/v1/clientes"):
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if p == "/v1/os" and request.method == "GET":
        return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})
    if "/cotacoes" in p and request.method == "GET":
        return httpx.Response(200, json={
            "data": _COTACOES,
            "estado_cotacao": "cotado",
            "selecionado": {"vf": "87.35", "cp": "200.91", "vo": "212.96",
                            "acrescimo_fornecedor_pct": "130", "markup_orcamento_pct": "6"},
        })
    if "/cotacoes" in p and request.method == "POST":
        return httpx.Response(201, json={"data": {"id": 9}})
    if "/selecionar" in p:
        return httpx.Response(200, json={"data": {"id": 9, "selecionada": True}})
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
    assert "Fornecedor" in grade._linhas_display()[0]["tipo"]
    assert "Aguardando" in grade._linhas_display()[0]["tipo"]


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
    assert grade.valor()[0]["tipo"] == "fornecedor"


# ------------------------------------------------------- DialogoCotacoes


def test_dialogo_mostra_tabela_com_vf_e_snapshot(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "Hot stamping"})
    # tabela tem as duas cotações
    assert dialogo._tabela.rowCount() == 2
    # VF na primeira linha (selecionada)
    assert "87.35" in dialogo._tabela.item(0, 1).text()
    # snapshot visível
    assert "VF: R$ 87.35" in dialogo._lbl_snapshot.text()
    assert "CP: R$ 200.91" in dialogo._lbl_snapshot.text()
    assert "VO: R$ 212.96" in dialogo._lbl_snapshot.text()
    # estado: cotado
    assert "cotado" in dialogo._lbl_estado.text().lower()


def test_dialogo_sem_item_salvo_desabilita(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"descricao_avulsa": "X"})  # sem id
    assert not dialogo._btn_lancar.isEnabled()
    assert not dialogo._tabela.isEnabled()


def test_dialogo_sem_cotacoes_mostra_orientacao(app):
    def handler_vazio(request):
        if "/cotacoes" in request.url.path:
            return httpx.Response(200, json={"data": [], "estado_cotacao": "aguardando", "selecionado": None})
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_vazio))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    assert dialogo._tabela.rowCount() == 0
    assert "aguardando" in dialogo._lbl_estado.text().lower()


def test_dialogo_vf_restrito_para_operador(app):
    """Sem `ver_custo_terceiro`, o servidor omite vf — o diálogo mostra (restrito)."""
    def handler_operador(request):
        if "/cotacoes" in request.url.path:
            return httpx.Response(200, json={
                "data": [{"id": 1, "fornecedor_id": 3, "fornecedor_nome": "Laminadora",
                          "prazo_dias": 5, "validade": None, "selecionada": True,
                          "criado_em": "2026-10-27T10:00:00"}],  # SEM vf
                "estado_cotacao": "cotado",
                "selecionado": None,  # SEM snapshot
            })
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_operador))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    assert "(restrito)" in dialogo._tabela.item(0, 1).text()
    assert dialogo._lbl_snapshot.text() == ""  # snapshot não veio


def _sem_dialogos(monkeypatch):
    """Evita QMessageBox modal travar o offscreen."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))


def test_dialogo_lancar_valida_campos_obrigatorios(app, monkeypatch):
    _sem_dialogos(monkeypatch)
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._campo_fornecedor.definir(None)  # sem fornecedor
    dialogo._lancar()
    assert dialogo._btn_lancar.isEnabled()
    assert dialogo._btn_lancar.text() == "Lançar cotação"


def test_dialogo_lancar_envia_payload_e_limpa(app, monkeypatch):
    _sem_dialogos(monkeypatch)
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._campo_fornecedor.definir(3)  # Laminadora
    dialogo._campo_vf.definir("50")  # VF 50
    dialogo._campo_prazo.definir("7")
    dialogo._check_selecionar.definir(True)

    dialogo._lancar()
    assert dialogo._btn_lancar.isEnabled()
    assert dialogo._campo_vf.valor() is None
    assert not dialogo._check_selecionar.valor()


def test_dialogo_selecionar_exige_linha(app, monkeypatch):
    _sem_dialogos(monkeypatch)
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._tabela.clearSelection()
    dialogo._selecionar()  # sem linha: só avisa, não explode
    assert dialogo._btn_selecionar.text() == "Selecionar marcada"


def test_dialogo_selecionar_envia_e_recarrega(app, monkeypatch):
    _sem_dialogos(monkeypatch)
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._tabela.selectRow(1)  # Gráfica B (id=2, não selecionada)
    dialogo._selecionar()
    assert dialogo._btn_selecionar.isEnabled()
    assert dialogo._btn_selecionar.text() == "Selecionar marcada"


# ------------------------------------------------------- Api (rotas de cotacao)


def test_api_cotacoes_rota_correta(app):
    chamadas: list[str] = []

    def handler_com_registro(request):
        chamadas.append(f"{request.method} {request.url.path}")
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_com_registro))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    api.listar_cotacoes(7, 10)
    assert "GET /v1/os/7/itens/10/cotacoes" in chamadas

    api.lancar_cotacao(7, 10, {"fornecedor_id": 3, "vf": "50.00"})
    assert "POST /v1/os/7/itens/10/cotacoes" in chamadas

    api.selecionar_cotacao(7, 10, 99)
    assert "PUT /v1/os/7/itens/10/cotacoes/99/selecionar" in chamadas
