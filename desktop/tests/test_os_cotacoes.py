"""Testes da UI de orçamento: grade de precificação e modal de cotações."""

from __future__ import annotations

import httpx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QRadioButton

from printgest.core.api import Api
from printgest.ui.grade_itens import GradeItens, calcular_preco
from printgest.ui.modulos.os import DialogoCotacoes

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
    if p.startswith("/v1/funcionarios") or p.startswith("/v1/clientes"):
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
    return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})


def _api():
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "Admin", "login": "admin", "nivel_acesso": "admin"}})
    return api


# ------------------------------------------------------------- GradeItens


def test_grade_adiciona_item_de_fornecedor(app):
    grade = GradeItens(api=_api())
    grade._check_fornecedor.setChecked(True)
    grade._descricao.setText("Hot stamping fosco")
    grade._adicionar()
    assert grade._itens[0]["tipo"] == "fornecedor"
    assert "Aguardando" in grade._linhas_display()[0]["tipo"]
    assert grade.itens_pendentes()


def test_calculo_vf_cp_vo(app):
    cp, vo = calcular_preco("87.35")
    assert str(cp) == "200.91"
    assert str(vo) == "212.96"


def test_vf_digitado_na_grade_gera_cp_e_preco(app):
    grade = GradeItens(api=_api())
    grade._check_fornecedor.setChecked(True)
    grade._descricao.setText("Adesivo Vinil")
    grade._vf.setText("35,00")
    grade._adicionar()

    item = grade.valor()[0]
    assert item["vf"] == "35.00"
    assert item["custo"] == "80.50"
    assert item["valor_unitario"] == "85.33"
    assert not grade.itens_pendentes()


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
    assert grade._itens[0]["estado_cotacao"] == "cotado"
    assert "Cotado" in grade._linhas_display()[0]["tipo"]


def test_grade_item_selecionado_devolve_dados_internos(app):
    grade = GradeItens(api=_api())
    grade.definir([
        {"id": 10, "tipo": "fornecedor", "descricao_avulsa": "Hot stamping",
         "quantidade": "1", "valor_unitario": "0", "desconto": "0"},
    ])
    grade._tabela.selectRow(0)
    assert grade.item_selecionado["id"] == 10


def test_valor_unitario_editavel_direto_na_grade(app):
    grade = GradeItens(api=_api())
    grade.definir([{
        "id": 10, "tipo": "proprio", "descricao_avulsa": "Impressão",
        "quantidade": "2", "valor_unitario": "10", "desconto": "0",
    }])

    celula = grade._tabela.item(0, 6)  # Preço Unit.
    assert celula.flags() & Qt.ItemFlag.ItemIsEditable
    celula.setText("12,50")
    assert grade.valor()[0]["valor_unitario"] == "12.50"
    assert not grade._tabela.item(0, 5).flags() & Qt.ItemFlag.ItemIsEditable


def test_item_aguardando_cotacao_tem_aviso_visual(app):
    grade = GradeItens(api=_api())
    grade._check_fornecedor.setChecked(True)
    grade._descricao.setText("Adesivo Vinil")
    grade._adicionar()

    assert "⚠" in grade._linhas_display()[0]["tipo"]
    assert grade._linhas_display()[0]["valor_unitario"] == "Aguard. Cotação"
    assert not grade._aviso_pendente.isHidden()
    assert grade._tabela.cellWidget(0, 10) is not None


def test_selecao_de_item_abre_formulario_de_edicao(app):
    grade = GradeItens(api=_api())
    grade.definir([{
        "id": 10, "tipo": "proprio", "descricao_avulsa": "Impressão",
        "quantidade": "2", "valor_unitario": "10", "desconto": "0",
    }])
    grade._tabela.selectRow(0)

    assert grade._btn_adicionar.text() == "Salvar item"
    assert grade._unit.text() == "10"
    grade._unit.setText("12")
    grade._adicionar()

    assert grade.valor()[0]["valor_unitario"] == "12"
    assert grade._btn_adicionar.text() == "+ Adicionar Novo Item"


def test_grade_resumo_e_estado_vazio(app):
    grade = GradeItens(api=_api())
    assert "Nenhum item" in grade._tabela._vazio.text()

    grade._descricao.setText("Serviço avulso")
    grade._adicionar()

    assert grade._resumo.text().startswith("Itens (1):")


# ------------------------------------------------------- DialogoCotacoes


def test_dialogo_mostra_tabela_com_vf_e_snapshot(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "Hot stamping"})
    assert dialogo._tabela.rowCount() == 2
    assert "87.35" in dialogo._tabela.item(0, 1).text()
    assert isinstance(dialogo._tabela.cellWidget(0, 0), QComboBox)
    assert isinstance(dialogo._tabela.cellWidget(0, 4), QRadioButton)
    assert "VF: R$ 87.35" in dialogo._lbl_snapshot.text()
    assert "Preço Unit.: R$ 212.96" in dialogo._lbl_snapshot.text()
    assert "aprovada" in dialogo._lbl_estado.text().lower()


def test_dialogo_sem_item_salvo_desabilita(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"descricao_avulsa": "X"})
    assert not dialogo._btn_aprovar.isEnabled()


def test_dialogo_sem_cotacoes_mostra_orientacao(app):
    def handler_vazio(request):
        if "/cotacoes" in request.url.path and request.method == "GET":
            return httpx.Response(200, json={"data": [], "estado_cotacao": "aguardando", "selecionado": None})
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_vazio))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    assert dialogo._tabela.rowCount() == 0
    assert "aguardando" in dialogo._lbl_estado.text().lower()


def test_dialogo_vf_restrito_para_operador(app):
    def handler_operador(request):
        if "/cotacoes" in request.url.path and request.method == "GET":
            return httpx.Response(200, json={
                "data": [{"id": 1, "fornecedor_id": 3, "fornecedor_nome": "Laminadora",
                          "prazo_dias": 5, "validade": None, "selecionada": True}],
                "estado_cotacao": "cotado", "selecionado": None,
            })
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_operador))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    assert "(restrito)" in dialogo._tabela.item(0, 1).text()
    assert dialogo._lbl_snapshot.text() == ""


def test_dialogo_radio_exclusivo(app):
    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    radio = dialogo._tabela.cellWidget(1, 4)
    radio.setChecked(True)
    outro = dialogo._tabela.cellWidget(0, 4)
    assert not outro.isChecked()


def test_dialogo_aprovar_envia_vf_e_devolve_snapshot(app, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QDialog, "accept", lambda self: None)

    dialogo = DialogoCotacoes(None, _api(), 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._tabela.item(0, 1).setText("50,00")
    radio = dialogo._tabela.cellWidget(0, 4)
    radio.setChecked(True)

    dialogo._aprovar()

    assert dialogo.aprovado["vo"] == "212.96"
    assert dialogo._btn_aprovar.isEnabled()
    assert dialogo._btn_aprovar.text() == "Aprovar Cotação"


def test_dialogo_aprovar_existente_usa_put_sem_duplicar(app, monkeypatch):
    from PySide6.QtWidgets import QDialog

    chamadas: list[str] = []

    def handler_com_registro(request):
        chamadas.append(f"{request.method} {request.url.path}")
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler_com_registro))
    api.autenticar({"token": "t", "usuario": {"id": 1, "nome": "Admin", "nivel_acesso": "admin"}})
    monkeypatch.setattr(QDialog, "accept", lambda self: None)

    dialogo = DialogoCotacoes(None, api, 7, {"id": 10, "descricao_avulsa": "X"})
    dialogo._tabela.cellWidget(0, 4).setChecked(True)
    dialogo._aprovar()

    assert any(c.startswith("PUT") and "/selecionar" in c for c in chamadas)
    assert not any(c.startswith("POST") and c.endswith("/cotacoes") for c in chamadas)


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
