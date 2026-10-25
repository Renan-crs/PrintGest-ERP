"""Testes do PDV / Venda de Balcão (duas visões) contra um daemon fictício."""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtCore import Qt
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
    {
        "id": 5,
        "codigo": "B015",
        "nome": "Adesivo Frosted 3mm",
        "preco_venda": "100.00",
        "codigo_barras": "7891000100103",
    }
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


# --- Revisão PDV out/2026 (Fase A — itens 1 a 8 e 17) ---------------------------


def test_estado_vazio_da_lista_de_itens_orienta(app, pumpar, pagina):
    """Sem itens: mensagem + atalhos no lugar do vazio (revisão nº 1)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    editor = pagina._itens_editor
    assert editor._pilha_itens.currentIndex() == 1  # estado vazio visível
    assert "Busque um produto ou serviço" in editor._pilha_itens.currentWidget().findChild(QLabel).text()

    _adicionar_item(pagina)
    assert editor._pilha_itens.currentIndex() == 0  # tabela de volta
    assert editor._tabela.rowCount() == 1
    editor._remover_linha(0)
    assert editor._pilha_itens.currentIndex() == 1  # vazio de novo


def test_busca_sem_chip_enter_e_placeholder_curto(app, pumpar, pagina):
    """Placeholder curto, sem o chip “Enter” que parecia um botão (nº 3)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    editor = pagina._itens_editor
    assert editor._entrada.placeholderText() == "Código, nome ou código de barras"
    chips = [
        w for w in editor._entrada.parentWidget().findChildren(QLabel)
        if w.property("kbdHint") == "true"
    ]
    assert chips == []


def test_codigo_de_barras_exato_adiciona_direto(app, pumpar, pagina, monkeypatch):
    """Bipe: EAN exato entra sem lista; foco volta à busca (revisão nº 3)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    editor = pagina._itens_editor
    voltas = []
    monkeypatch.setattr(editor, "focar_busca", lambda: voltas.append(True))
    editor._entrada.setText("7891000100103")
    editor._adicionar_pela_busca()
    assert editor._tabela.rowCount() == 1
    assert editor._itens[0]["produto_id"] == 5
    assert voltas == [True]  # foco devolvido à busca para o próximo bipe


def test_busca_com_varios_candidatos_abre_lista_navegavel(app, pumpar, pagina, monkeypatch):
    """Vários resultados: popup navegável em vez de “não encontrado” (nº 3)."""
    import printgest.ui.modulos.venda_balcao as mod

    extras = [
        {"id": 6, "codigo": "B016", "nome": "AdesivoTransparente 2mm",
         "preco_venda": "50.00", "codigo_barras": None},
        {"id": 7, "codigo": "B017", "nome": "AdesivoEspelhado 2mm",
         "preco_venda": "60.00", "codigo_barras": None},
    ]
    original = mod.EditorItensVenda._produtos_recebidos

    def com_extras(self, saida):
        original(self, saida)
        self._produtos.update({
            r["id"]: r for r in extras
        })
        for r in extras:
            self._por_nome[r["nome"].lower()] = r["id"]

    monkeypatch.setattr(mod.EditorItensVenda, "_produtos_recebidos", com_extras)
    editor = pagina._itens_editor
    editor.carregar(pagina._api)
    pumpar(lambda: "adesivoespelhado 2mm" in editor._por_nome)

    editor._entrada.setText("adesivo")
    chamado = []
    monkeypatch.setattr(
        editor._completer, "complete", lambda *a: chamado.append(True)
    )
    editor._adicionar_pela_busca()
    assert chamado == [True]  # abriu a lista, não adds nem warning
    assert editor._tabela.rowCount() == 0


def test_finalizar_desabilitado_sem_itens_e_habilita_ao_adicionar(app, pumpar, pagina):
    """Finalizar com 0 itens: desabilitado + dica (revisão nº 4)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    assert pagina._btn_salvar.isEnabled() is False
    assert "Adicione ao menos 1 item" in pagina._btn_salvar.toolTip()

    _adicionar_item(pagina)
    assert pagina._btn_salvar.isEnabled() is True
    assert pagina._btn_salvar.toolTip() == "Finalizar venda (F9)"

    pagina._itens_editor._remover_linha(0)
    assert pagina._btn_salvar.isEnabled() is False


def test_desconto_por_item_na_grade_entra_no_total(app, pumpar, pagina):
    """Coluna Desc. editável; desconto da linha entra no total (nº 2)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    editor = pagina._itens_editor
    _adicionar_item(pagina)

    coluna = editor._COL_DESC_ITEM
    editor._tabela.item(0, coluna).setText("10")  # -10 no item de R$ 100
    assert editor._itens[0]["desconto"] == "10"
    assert editor._tabela.item(0, editor._COL_TOTAL).text() == "R$ 90,00"
    assert pagina._lbl_total.text() == "R$ 90,00"
    # e vai no payload
    assert editor.valor()[0]["desconto"] == "10"

    # desconto negativo não passa: vira 0
    editor._tabela.item(0, coluna).setText("-5")
    assert editor._itens[0]["desconto"] == "0"


def test_colunas_numericas_alinhadas_a_direita(app, pumpar, pagina):
    """Qtd/Unit/Desc/Total alinhadas à direita (revisão nº 2)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    editor = pagina._itens_editor
    esperado = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    for coluna in (
        editor._COL_QTD,
        editor._COL_UNIT,
        editor._COL_DESC_ITEM,
        editor._COL_TOTAL,
    ):
        assert editor._tabela.item(0, coluna).textAlignment() == esperado


def test_falta_quando_recebido_nao_cobre_e_troco_quando_cobre(app, pumpar, pagina):
    """“Falta R$ X” em aviso; troco em verde quando cobre (nº 7)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)  # total R$ 100
    pagina._recebido.definir("40")
    assert pagina._lbl_troco_rotulo.text() == "FALTA"
    assert pagina._lbl_troco.text() == "R$ 60,00"
    assert pagina._lbl_troco.property("role") == "atencao"

    pagina._recebido.definir("150")
    assert pagina._lbl_troco_rotulo.text() == "TROCO"
    assert pagina._lbl_troco.text() == "R$ 50,00"
    assert pagina._lbl_troco.property("role") == "success"

    # sem valor digitado: não grita “falta”
    pagina._recebido.definir(None)
    assert pagina._lbl_troco_rotulo.text() == "TROCO"


def test_resumo_tem_desconto_e_total_em_destaque(app, pumpar, pagina):
    """Bloco Subtotal/Desconto/Total com o Total em 28 px (nº 7)."""
    pumpar(lambda: "b015" in pagina._itens_editor._por_codigo)
    _adicionar_item(pagina)
    pagina._desconto.definir("25")
    assert pagina._lbl_desconto_totais.text() == "R$ 25,00"
    assert pagina._lbl_subtotal.text() == "R$ 100,00"
    assert pagina._lbl_total.text() == "R$ 75,00"
    assert pagina._lbl_total.objectName() == "totalPdv"


def test_resumo_fica_colado_na_barra_de_acoes(app, pumpar, pagina):
    """Resumo imediatamente acima do botão primário (nº 7/14)."""
    from PySide6.QtWidgets import QPushButton

    painel = pagina._lbl_total.parentWidget()  # cardLow do resumo
    coluna = painel.parentWidget().layout()
    idx_resumo = idx_acoes = None
    for i in range(coluna.count()):
        item = coluna.itemAt(i)
        wid = item.widget()
        if wid is painel:
            idx_resumo = i
        elif wid is not None and pagina._btn_salvar in wid.findChildren(QPushButton):
            idx_acoes = i
    assert idx_resumo is not None
    assert idx_acoes is not None
    assert idx_acoes - idx_resumo == 1  # nada entre o resumo e a barra


def test_wrappers_sem_faixa_cinza(app, pumpar, pagina):
    """Rótulos/checkboxes sobre fundo transparente (revisão nº 5)."""
    for wrapper in (
        pagina._campo_cliente,
        pagina._campo_vendedor,
        pagina._campo_troco,
        pagina._itens_editor._barra_editor(),
    ):
        assert wrapper.objectName() == "caixaForma"
    # checkbox sem faixa: QSS global (testado como texto do tema)
    from printgest.ui.theme import _QSS

    assert "QCheckBox, QRadioButton" in _QSS
    assert "background: transparent; /* sem faixa cinza atrás" in _QSS


def test_combo_vendedor_tem_placeholder(app, pumpar, pagina):
    """Vendedor vazio com placeholder, sem seleção silenciosa (nº 6)."""
    pumpar(lambda: pagina._vendedor.widget.count() > 0)
    combo = pagina._vendedor.widget
    assert combo.placeholderText() == "Selecione o vendedor"
    assert combo.currentIndex() == -1
    assert pagina._vendedor.valor() is None


def test_fonte_unica_sem_consolas_no_total(app):
    """Total/cabeçalho na família única do app — sem monoespaçada (nº 2/8).

    `Consolas` continua só no valor digitado da chave de produto (regra
    `QLineEdit[mono="true"]`) — monoespaçada é desejável ali (revisão nº 5 da
    tela de ativação); o que sai é o fallback do Total/métricas.
    """
    from printgest.ui import theme

    assert '"Inter", "Consolas"' not in theme._QSS  # regra antiga do valorCard
    assert "totalPdv" in theme._QSS
    assert isinstance(theme._resolver_familia(), str)
    assert theme.FONT_RESOLVIDA in ("Inter", "Segoe UI")


def test_seta_do_combo_vem_de_svg_embutido(app):
    """Seta de QComboBox por imagem SVG — sem a barra escura nativa (nº 6)."""
    from pathlib import Path

    from printgest.ui import theme

    assert "%asset_seta%" in theme._QSS
    svg = theme._ASSETS / "seta-combo.svg"
    assert svg.exists() and svg.stat().st_size > 0


def test_mira_sobre_nova_os_nao_existe_no_codigo(app):
    """Item 17: nenhuma sobreposição/efeito decorativo sobre o botão Nova OS."""
    efeitos = [
        w.graphicsEffect()
        for w in pagina_efeitos() if w.graphicsEffect() is not None
    ]
    assert efeitos == []


def pagina_efeitos():
    """Widgets que poderiam desenhar círculos translúcidos na barra do PDV."""
    from PySide6.QtWidgets import QWidget

    return [
        w for w in QWidget.findChildren(QApplication_active(), QWidget)
        if w.objectName() in {"chaveRapida"} or type(w).__name__ == "QPushButton"
    ]


def QApplication_active():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance()
