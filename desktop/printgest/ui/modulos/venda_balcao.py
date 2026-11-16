"""Módulo Movimento — PDV / Venda de Balcão (mockups 3.4 + spec §3.1/§3.2).

A tela tem **duas visões**, na linha da reestruturação recomendada (spec 3.2):

- **Nova venda** (padrão, F6): busca de produto/serviço com Enter para
  adicionar, grade de itens e painel de pagamento à direita — sem rolagem
  horizontal e com *Finalizar venda* sempre visível.
- **Histórico**: lista de vendas em largura total (busca Ctrl+F, filtros,
  paginação, exportação e cancelamento).

Vendas são imutáveis na API (`POST /v1/vendas` cria, `DELETE /{id}` cancela,
não há PUT). O contrato enviado (`VendaCreate`/`VendaItemIn`) permanece o
mesmo — a venda não usa dimensões (isso é do fluxo de O.S.).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QToolButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.api import Api
from printgest.core.dominio import FORMAS_PAGAMENTO
from printgest.core.rbac import pode_abrir
import printgest.core.tarefas as tarefas
from printgest.ui.busca import CampoBusca
from printgest.ui.formulario import (
    CampoCheck,
    CampoCombo,
    CampoTexto,
    CampoValor,
    em_volta,
    formatar_data_iso,
    formatar_moeda,
    limpo,
    para_decimal,
    rotulo_secao,
)
from printgest.ui.modulos.condicao_pagamento import CondicaoPagamentoCliente
from printgest.ui.paginador import LOTE, Paginador
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    aplicar_estilo,
    estado_primario,
    estado_sucesso,
    estado_erro,
    estado_muted,
    estado_atencao,
    estado_danger,
    estado_secundario,
)

# Formas que aceitam parcelamento (mostram o campo "Parcelas").
FORMAS_PAGAMENTO_PARCELAVEIS = {"cartao_credito", "boleto", "fiado"}
# Troco só faz sentido em dinheiro.
_FORMA_DINHEIRO = "dinheiro"

_ROTULO_PAGAMENTO = dict(FORMAS_PAGAMENTO)
_ROTULO_STATUS = {"ok": "Finalizada", "cancelado": "Cancelada"}


# --------------------------------------------------------------- utilitários


def _dec(valor) -> Decimal:
    """Decimal tolerante ao formato brasileiro ('1.234,56'); vazio/inválido → 0."""
    dec = para_decimal(valor)
    return Decimal("0") if dec is None else dec


def _texto_numero(valor) -> str:
    """Decimal → texto compacto para edição ('2'; '1.5' → '1,5')."""
    dec = _dec(valor)
    if dec == dec.to_integral_value():
        return str(int(dec))
    return f"{dec:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _texto_moeda_editavel(valor) -> str:
    """Valor decimal em edição — sem prefixo, 2 casas, vírgula decimal."""
    return f"{_dec(valor):.2f}".replace(".", ",")


def _campo_rotulado(rotulo: str, widget: QWidget) -> QWidget:
    """Rótulo acima do campo (padrão dos formulários do sistema).

    Rótulo em caixa normal (não UPPERCASE) — hierarquia sem gritar e contraste
    legível (revisão PDV P1#11).
    """
    caixa = QWidget()
    caixa.setObjectName("caixaForma")  # fundo transparente: sem faixa cinza
    col = QVBoxLayout(caixa)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    label = QLabel(rotulo)
    label.setObjectName("labelForm")
    col.addWidget(label)
    col.addWidget(widget)
    return caixa


# ----------------------------------------------------------- grade de itens


class EditorItensVenda(QWidget):
    """Grade de itens da venda com busca por produto e edição de qtd/valor.

    Cada linha guarda o contrato de `VendaItemIn`
    (`{produto_id, descricao_avulsa, quantidade, valor_unitario, desconto}`).
    O campo **Dimensões** não pertence à venda (é do fluxo de O.S. — spec C9).
    """

    alterado = Signal()
    largo = True

    _COL_SEQ = 0
    _COL_DESC = 1
    _COL_QTD = 2
    _COL_UNIT = 3
    _COL_DESC_ITEM = 4
    _COL_TOTAL = 5
    _COL_REM = 6

    _CABECALHOS = ["#", "Descrição", "Qtd", "Valor unit.", "Desc.", "Total", ""]

    def __init__(self, api: Api | None = None) -> None:
        super().__init__()
        self._api = api
        self._itens: list[dict] = []
        self._produtos: dict[int, dict] = {}
        self._por_codigo: dict[str, int] = {}
        self._por_nome: dict[str, int] = {}
        self._rotulos: dict[str, int] = {}
        self._montando = False

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        col.addWidget(self._barra_editor())
        col.addWidget(self._tabela_itens(), 1)
        # Estado vazio como OVERLAY sobre a tabela: os cabeçalhos de coluna
        # ficam sempre visíveis, mesmo sem itens (P1#7).
        self._vazio_itens = self._estado_vazio_itens()
        self._vazio_itens.setParent(self._tabela.viewport())
        self._vazio_itens.raise_()

        if api is not None:
            self.carregar(api)

    # -------------------------------------------------------------- editor

    def _barra_editor(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("caixaForma")
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)

        self._entrada = QLineEdit()
        self._entrada.setPlaceholderText("Código, nome ou código de barras")
        self._entrada.setClearButtonEnabled(True)
        self._entrada.setMinimumHeight(40)
        self._entrada.returnPressed.connect(self._adicionar_pela_busca)
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.activated[str].connect(self._adicionar_do_texto)
        self._entrada.setCompleter(self._completer)
        linha.addWidget(self._entrada, 1)

        rotulo = QLabel("QTD")
        rotulo.setObjectName("labelForm")
        linha.addWidget(rotulo)
        self._qtd_add = QLineEdit("1")
        self._qtd_add.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._qtd_add.setFixedWidth(64)
        self._qtd_add.setMinimumHeight(40)
        self._qtd_add.setToolTip("Quantidade (aceita casas decimais, ex.: 2,5)")
        linha.addWidget(self._qtd_add)

        self._btn_adicionar = QPushButton("Adicionar")
        estado_primario(self._btn_adicionar)
        self._btn_adicionar.setMinimumHeight(40)
        self._btn_adicionar.clicked.connect(self._adicionar_pela_busca)
        linha.addWidget(self._btn_adicionar)

        self._btn_avulso = QPushButton("Item avulso")
        self._btn_avulso.setMinimumHeight(40)
        self._btn_avulso.setToolTip(
            "Adiciona um item sem produto, usando o texto digitado como descrição"
        )
        self._btn_avulso.clicked.connect(self._adicionar_avulso)
        linha.addWidget(self._btn_avulso)
        return caixa

    def _estado_vazio_itens(self) -> QWidget:
        """Instrução única com chips de atalho fixos (P1#8) — overlay da tabela."""
        caixa = QWidget()
        col = QVBoxLayout(caixa)
        col.setContentsMargins(12, 24, 12, 24)
        col.addStretch(2)
        titulo = QLabel("🔍 Busque um produto/serviço e pressione Enter para adicionar")
        titulo.setObjectName("vazioTabela")
        titulo.setWordWrap(True)
        titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(titulo, 0, Qt.AlignmentFlag.AlignHCenter)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addStretch(1)
        for texto in ("Ctrl+F busca", "F9 finaliza", "Esc limpa (com confirmação)"):
            chip = QLabel(texto)
            chip.setProperty("badge", "true")
            aplicar_estilo(chip)
            chips.addWidget(chip)
        chips.addStretch(1)
        col.addLayout(chips, 0)
        col.addStretch(3)
        return caixa

    def _tabela_itens(self) -> QTableWidget:
        self._tabela = QTableWidget(0, len(self._CABECALHOS))
        self._tabela.setHorizontalHeaderLabels(self._CABECALHOS)
        self._tabela.verticalHeader().setVisible(False)
        # Linhas de 40 px: alvo de toque confortável e leitura sem aperto (P1#7).
        self._tabela.verticalHeader().setDefaultSectionSize(40)
        self._tabela.setShowGrid(False)
        self._tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tabela.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._tabela.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._tabela.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        cab = self._tabela.horizontalHeader()
        cab.setStretchLastSection(False)
        cab.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(self._COL_DESC, QHeaderView.ResizeMode.Stretch)
        cab.setSectionResizeMode(self._COL_REM, QHeaderView.ResizeMode.Fixed)
        self._tabela.setColumnWidth(self._COL_REM, 34)
        self._tabela.setMinimumHeight(160)
        self._tabela.itemChanged.connect(self._linha_mudou)
        return self._tabela

    # ------------------------------------------------------------ produtos

    def carregar(self, api: Api) -> None:
        self._api = api
        catalogos.carregar(
            "produtos",
            lambda: api.listar("produtos", limit=1000),
            on_ok=self._produtos_recebidos,
        )

    def _produtos_recebidos(self, saida: dict) -> None:
        self._produtos = {
            r["id"]: {
                "nome": r.get("nome", ""),
                "codigo": r.get("codigo", ""),
                "codigo_barras": r.get("codigo_barras"),
                "preco_venda": r.get("preco_venda"),
            }
            for r in saida.get("data", [])
        }
        self._por_codigo = {}
        self._por_nome = {}
        self._rotulos = {}
        for pid, produto in self._produtos.items():
            codigo = str(produto.get("codigo") or "").strip()
            barras = str(produto.get("codigo_barras") or "").strip()
            nome = str(produto.get("nome") or "").strip()
            # Código de barras exato adiciona direto (bipe) — revisão nº 3.
            for chave in (codigo, barras):
                if chave:
                    self._por_codigo[chave.lower()] = pid
            if nome:
                self._por_nome[nome.lower()] = pid
            rotulo = f"{codigo} • {nome}".strip(" •")
            if rotulo:
                self._rotulos[rotulo] = pid
        self._completer.setModel(QStringListModel(sorted(self._rotulos)))

    def _resolver_produto(self, texto: str):
        alvo = texto.strip().lower()
        if not alvo:
            return None
        if alvo in self._por_codigo:
            return self._por_codigo[alvo]
        if alvo in self._por_nome:
            return self._por_nome[alvo]
        for rotulo, pid in self._rotulos.items():
            if rotulo.lower() == alvo:
                return pid
        candidatos = {
            pid for nome, pid in self._por_nome.items() if nome.startswith(alvo)
        }
        if len(candidatos) == 1:
            return candidatos.pop()
        return None

    def _candidatos(self, texto: str) -> set[int]:
        """Produtos cujo nome/código contém o texto (para decidir Enter)."""
        alvo = texto.strip().lower()
        if not alvo:
            return set()
        diretos = {
            pid
            for chave, pid in self._por_codigo.items()
            if alvo in chave
        }
        nomes = {
            pid for nome, pid in self._por_nome.items() if alvo in nome
        }
        return diretos | nomes

    # ------------------------------------------------------------- itens

    def focar_busca(self) -> None:
        self._entrada.setFocus()
        self._entrada.selectAll()

    def _adicionar_pela_busca(self) -> None:
        texto = self._entrada.text().strip()
        if not texto:
            self.focar_busca()
            return
        pid = self._resolver_produto(texto)
        if pid is None:
            # Vários candidatos: abre a lista navegável (↑/↓ + Enter) em vez de
            # brigar com o operador (revisão nº 3).
            candidatos = self._candidatos(texto)
            if len(candidatos) > 1:
                self._completer.setCompletionPrefix(texto)
                self._completer.complete()
                return
            if len(candidatos) == 1:
                pid = candidatos.pop()
            else:
                QMessageBox.warning(
                    self,
                    "Item",
                    f"Produto ou serviço não encontrado: “{texto}”.\n"
                    "Use “Item avulso” para lançar uma descrição livre.",
                )
                return
        self._adicionar_produto(pid)

    def _adicionar_do_texto(self, texto: str) -> None:
        self._entrada.setText(texto)
        self._adicionar_pela_busca()

    def _adicionar_produto(self, produto_id) -> None:
        produto = self._produtos.get(produto_id, {})
        self._itens.append(
            {
                "produto_id": produto_id,
                "descricao_avulsa": None,
                "quantidade": str(_qtd_valida(self._qtd_add.text())),
                "valor_unitario": str(_dec(produto.get("preco_venda"))),
                "desconto": "0",
            }
        )
        self._limpar_entrada()
        self._atualizar()

    def _adicionar_avulso(self) -> None:
        descricao = self._entrada.text().strip()
        if not descricao:
            QMessageBox.information(
                self, "Item avulso", "Digite a descrição do item na busca."
            )
            return
        self._itens.append(
            {
                "produto_id": None,
                "descricao_avulsa": descricao,
                "quantidade": str(_qtd_valida(self._qtd_add.text())),
                "valor_unitario": "0",
                "desconto": "0",
            }
        )
        self._limpar_entrada()
        self._atualizar()

    def _limpar_entrada(self) -> None:
        self._entrada.clear()
        self._qtd_add.setText("1")
        self.focar_busca()

    def _remover_linha(self, linha: int) -> None:
        if 0 <= linha < len(self._itens):
            del self._itens[linha]
            self._atualizar()

    def _linha_mudou(self, item: QTableWidgetItem) -> None:
        if self._montando:
            return
        linha = item.row()
        if linha < 0 or linha >= len(self._itens):
            return
        dado = self._itens[linha]
        if item.column() == self._COL_QTD:
            qtd = _qtd_valida(item.text())
            dado["quantidade"] = str(qtd)
            texto = _texto_numero(qtd)
        elif item.column() == self._COL_UNIT:
            unit = _dec(item.text())
            dado["valor_unitario"] = str(unit)
            texto = _texto_moeda_editavel(unit)
        elif item.column() == self._COL_DESC_ITEM:
            desc = max(Decimal("0"), _dec(item.text()))
            dado["desconto"] = str(desc)
            texto = _texto_moeda_editavel(desc)
        else:
            return
        self._montando = True
        item.setText(texto)
        self._tabela.item(linha, self._COL_TOTAL).setText(
            formatar_moeda(str(self._total_linha(linha)))
        )
        self._montando = False
        self._recalcular()

    # ------------------------------------------------------------ desenho

    def _descricao(self, item: dict) -> str:
        produto = self._produtos.get(item.get("produto_id"))
        return (
            (produto or {}).get("nome")
            or item.get("descricao_avulsa")
            or "—"
        )

    def _total_linha(self, linha: int) -> Decimal:
        item = self._itens[linha]
        return (
            _dec(item.get("valor_unitario")) * _dec(item.get("quantidade"))
            - _dec(item.get("desconto"))
        )

    @staticmethod
    def _celula(texto: str, direita: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(texto)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if direita:  # colunas numéricas alinhadas à direita (revisão nº 2)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        return item

    @staticmethod
    def _celula_editavel(texto: str) -> QTableWidgetItem:
        item = QTableWidgetItem(texto)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        return item

    def _atualizar(self) -> None:
        self._montando = True
        self._tabela.setRowCount(0)
        self._tabela.setRowCount(len(self._itens))
        for linha, item in enumerate(self._itens):
            self._tabela.setItem(
                linha, self._COL_SEQ, self._celula(f"{linha + 1:02d}")
            )
            self._tabela.setItem(
                linha, self._COL_DESC, self._celula(self._descricao(item))
            )
            self._tabela.setItem(
                linha,
                self._COL_QTD,
                self._celula_editavel(_texto_numero(item.get("quantidade"))),
            )
            self._tabela.setItem(
                linha,
                self._COL_UNIT,
                self._celula_editavel(_texto_moeda_editavel(item.get("valor_unitario"))),
            )
            self._tabela.setItem(
                linha,
                self._COL_DESC_ITEM,
                self._celula_editavel(
                    _texto_moeda_editavel(max(Decimal("0"), _dec(item.get("desconto"))))
                ),
            )
            self._tabela.setItem(
                linha,
                self._COL_TOTAL,
                self._celula(
                    formatar_moeda(str(self._total_linha(linha))), direita=True
                ),
            )
            botao = QPushButton("✕")
            botao.setObjectName("acaoLinha")
            botao.setToolTip("Remover item")
            botao.setFixedSize(26, 22)
            botao.clicked.connect(
                lambda _=False, alvo=linha: self._remover_linha(alvo)
            )
            self._tabela.setCellWidget(linha, self._COL_REM, botao)
        self._montando = False
        # Overlay do vazio por cima da tabela: cabeçalhos sempre visíveis.
        self._vazio_itens.setVisible(not self._itens)
        self._reposicionar_vazio()
        self._recalcular()

    def _reposicionar_vazio(self) -> None:
        """Ancora o overlay de vazio sobre a área útil da tabela."""
        if not hasattr(self, "_vazio_itens") or not hasattr(self, "_tabela"):
            return
        viewport = self._tabela.viewport()
        self._vazio_itens.setGeometry(viewport.rect())
        self._vazio_itens.raise_()

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API do Qt)
        super().resizeEvent(evento)
        self._reposicionar_vazio()

    def _recalcular(self) -> None:
        self.alterado.emit()

    def subtotal(self) -> Decimal:
        total = Decimal("0")
        for i in self._itens:
            total += _dec(i.get("valor_unitario")) * _dec(i.get("quantidade"))
            total -= _dec(i.get("desconto"))
        return total

    # ---------------------------------------------------------- formulário

    @property
    def widget(self) -> QWidget:
        return self

    def valor(self) -> list[dict]:
        return [
            {
                "produto_id": i.get("produto_id"),
                "descricao_avulsa": i.get("descricao_avulsa"),
                "quantidade": str(_dec(i.get("quantidade"))),
                "valor_unitario": str(_dec(i.get("valor_unitario"))),
                "desconto": str(_dec(i.get("desconto"))),
            }
            for i in self._itens
        ]

    def definir(self, lista) -> None:
        self._itens = [
            {
                "produto_id": i.get("produto_id"),
                "descricao_avulsa": i.get("descricao_avulsa"),
                "quantidade": str(_dec(i.get("quantidade"))),
                "valor_unitario": str(_dec(i.get("valor_unitario"))),
                "desconto": str(_dec(i.get("desconto"))),
            }
            for i in (lista or [])
        ]
        self._atualizar()

    def limpar(self) -> None:
        self._itens = []
        self._atualizar()

    def habilitar(self, ligado: bool) -> None:
        for widget in (
            self._entrada,
            self._qtd_add,
            self._btn_adicionar,
            self._btn_avulso,
            self._tabela,
        ):
            widget.setEnabled(ligado)


def _qtd_valida(texto) -> Decimal:
    qtd = _dec(texto)
    return Decimal("1") if qtd <= 0 else qtd


# ------------------------------------------------------------------- página


class PaginaVendaBalcao(CondicaoPagamentoCliente, QWidget):
    """PDV — duas visões (Nova venda / Histórico) sobre `POST/DELETE /v1/vendas`."""

    navegar = Signal(str)

    ROTULO_PAGINA = "PDV"
    ROTULO_EXPORTAR = "Exportar Excel"
    LUGAR_BUSCA = "Buscar por Nº da venda ou cliente..."
    CLIENTE_OPCAO_PADRAO = (None, "Consumidor final")
    CHAVES = [
        "numero",
        "data_venda",
        "cliente_nome",
        "forma_pagamento",
        "valor_total",
        "status",
        "fiscal",
        "acoes",
    ]
    COLUNAS = ["Nº", "Data", "Cliente", "Pagamento", "Total", "Status", "Fiscal", "Ações"]
    CHAVE_FILTRO = "status"
    FILTROS = [
        ("", "Todas"),
        ("ok", "Finalizadas"),
        ("cancelado", "Canceladas"),
    ]

    def __init__(
        self, api: Api, modo_leitura: bool = False, nivel: str | None = None
    ) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._nivel = nivel
        self._linhas: list[dict] = []
        self._total = 0
        self._offset = 0
        self._seq = 0
        self._filtro = ""
        self._total_venda = Decimal("0")
        self._caixa_fechado = False  # resolvido em `_verificar_caixa` (P0#3)
        self._iniciar_condicao_pagamento()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(self._barra_titulo())

        # M0 (PRD v3.0 §2): o PDV não opera com caixa fechado — o banner orienta
        # e leva direto à tela de abertura; o servidor continua sendo quem
        # bloqueia (409 "Caixa fechado").
        layout.addWidget(self._montar_banner_caixa())

        self._vistas = QStackedWidget()
        self._vista_venda = self._montar_vista_venda()
        self._vista_historico = self._montar_vista_historico()
        self._vistas.addWidget(self._vista_venda)
        self._vistas.addWidget(self._vista_historico)
        layout.addWidget(self._vistas, 1)

        self._conectar_campos()
        self._aplicar_modo_leitura()
        self._instalar_atalhos()
        self._limpar_form()
        self._ir_para_venda()
        self._carregar_clientes_flags()
        self._carregar_vendedores()
        self.recarregar()

    # -------------------------------------------------------------- topo

    def _barra_titulo(self) -> QWidget:
        """Cabeçalho mínimo (P1#6): título + alternância Nova venda/Histórico.

        "Nova venda" repetida dentro do próprio PDV, "Nova OS/Orçamento" (outro
        fluxo) e "Exportar Excel" (relatório) saem daqui — a exportação vive na
        vista Histórico, junto dos filtros.
        """
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)

        titulo = QLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        linha.addWidget(titulo)
        linha.addStretch(1)

        # P1#16 (PDV+Hist+OS): controle segmentado Venda | Histórico.
        self._botao_venda = QPushButton("Venda (F6)")
        self._botao_venda.setCheckable(True)
        self._botao_venda.setChecked(True)
        self._botao_venda.setObjectName("chaveRapida")
        self._botao_venda.setToolTip("Nova venda (F6)")
        self._botao_venda.clicked.connect(self._ir_para_venda)
        linha.addWidget(self._botao_venda)

        self._botao_historico = QPushButton("Histórico")
        self._botao_historico.setCheckable(True)
        self._botao_historico.setObjectName("chaveRapida")
        self._botao_historico.setToolTip("Histórico de vendas (Ctrl+F para buscar)")
        self._botao_historico.clicked.connect(self._ir_para_historico)
        linha.addWidget(self._botao_historico)
        return caixa

    # ------------------------------------------------------- vista venda

    def _montar_vista_venda(self) -> QWidget:
        pagina = QWidget()
        linha = QHBoxLayout(pagina)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)

        # Coluna esquerda (~60%): itens da venda.
        esquerda = QWidget()
        esquerda.setObjectName("card")
        col_e = QVBoxLayout(esquerda)
        col_e.setContentsMargins(14, 12, 14, 12)
        col_e.setSpacing(8)

        cabeca = QWidget()
        cabeca.setObjectName("caixaForma")
        h = QHBoxLayout(cabeca)
        h.setContentsMargins(0, 0, 0, 0)
        titulo = QLabel("ITENS DA VENDA")
        titulo.setObjectName("labelForm")
        h.addWidget(titulo)
        h.addStretch(1)
        self._lbl_resumo_itens = QLabel("0 itens")
        estado_muted(self._lbl_resumo_itens)
        h.addWidget(self._lbl_resumo_itens)
        col_e.addWidget(cabeca)

        self._itens_editor = EditorItensVenda(api=self._api)
        col_e.addWidget(self._itens_editor, 1)
        linha.addWidget(esquerda, 3)

        # Coluna direita (340–380 px): campos roláveis + Total/ações FIXOS no
        # rodapé do cartão — o painel inteiro nunca é cortado em 1024×768
        # (revisão PDV P0#1).
        direita = QWidget()
        direita.setObjectName("card")
        direita.setMinimumWidth(340)
        direita.setMaximumWidth(380)
        col_d = QVBoxLayout(direita)
        col_d.setContentsMargins(16, 14, 16, 14)
        col_d.setSpacing(10)

        titulo_pag = rotulo_secao("Pagamento")
        col_d.addWidget(titulo_pag)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        formulario = QWidget()
        col_f = QVBoxLayout(formulario)
        col_f.setContentsMargins(0, 0, 0, 0)
        col_f.setSpacing(10)

        self._cliente = CampoCombo("Cliente", [(None, "Consumidor final")])
        # Um único campo de cliente (P1#9): combo pesquisável; nome que não
        # casar com um cadastro vai como cliente avulso no payload.
        self._cliente.widget.setEditable(True)
        self._cliente.widget.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._completer_clientes = QCompleter(self)
        self._completer_clientes.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self._completer_clientes.setFilterMode(Qt.MatchFlag.MatchContains)
        self._cliente.widget.setCompleter(self._completer_clientes)
        self._vendedor = CampoCombo("Vendedor", [])
        self._vendedor.widget.setPlaceholderText("Selecione o vendedor")
        self._vendedor.widget.setCurrentIndex(-1)
        self._forma = CampoCombo("Forma de pagamento", FORMAS_PAGAMENTO)
        self._parcelas = CampoTexto("Parcelas", valor="1", maximo=2)
        self._recebido = CampoValor("Valor recebido")
        self._desconto = CampoValor("Desconto")

        for campo in (
            self._cliente,
            self._vendedor,
            self._forma,
            self._parcelas,
            self._recebido,
            self._desconto,
        ):
            # Altura mínima por controle: o QSS de padding não corta mais a
            # metade inferior do texto (P0#1/P0#4 da revisão PDV+Hist+OS).
            campo.widget.setMinimumHeight(40)
            # Campos de valor/texto expõem o editor interno (QLineEdit).
            if hasattr(campo, "edicao"):
                campo.edicao.setMinimumHeight(40)

        self._campo_cliente = _campo_rotulado("Cliente", self._cliente.widget)
        self._campo_vendedor = _campo_rotulado("Vendedor", self._vendedor.widget)
        self._campo_forma = _campo_rotulado(
            "Forma de pagamento", self._forma.widget
        )
        self._campo_parcelas = _campo_rotulado("Parcelas", self._parcelas.widget)
        self._campo_recebido = _campo_rotulado(
            "Valor recebido", self._recebido.widget
        )
        self._campo_desconto = _campo_rotulado("Desconto", self._desconto.widget)
        self._campo_troco = self._montar_troco()

        grade = QGridLayout()
        grade.setHorizontalSpacing(12)
        grade.setVerticalSpacing(10)
        grade.addWidget(self._campo_cliente, 0, 0, 1, 2)
        grade.addWidget(self._campo_vendedor, 1, 0, 1, 2)
        grade.addWidget(self._campo_forma, 2, 0)
        grade.addWidget(self._campo_parcelas, 2, 1)
        grade.addWidget(self._campo_recebido, 3, 0)
        grade.addWidget(self._campo_troco, 3, 1)
        grade.addWidget(self._campo_desconto, 4, 0)
        grade.setColumnStretch(0, 1)
        grade.setColumnStretch(1, 1)
        col_f.addLayout(grade)

        self._pagamento_confirmado = CampoCheck("Adiantamento/sinal já recebido")
        self._pagamento_confirmado.widget.setToolTip(
            "Marque quando o cliente exige pagamento antecipado (adiantamento "
            "total ou sinal) e o valor já foi recebido."
        )
        col_f.addWidget(self._pagamento_confirmado.widget)
        self._nfce = CampoCheck("Emitir NFC-e ao finalizar")
        col_f.addWidget(self._nfce.widget)
        col_f.addStretch(1)
        rolagem.setWidget(formulario)
        col_d.addWidget(rolagem, 1)

        # Resumo colado à barra de ações (revisão nº 7): Total e botões ficam
        # SEMPRE visíveis, fora da rolagem (P0#1/P2#12).
        col_d.addWidget(self._montar_totais())
        col_d.addWidget(self._montar_acoes())

        linha.addWidget(direita, 2)
        return pagina

    def _montar_troco(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("caixaForma")
        col = QVBoxLayout(caixa)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self._lbl_troco_rotulo = QLabel("TROCO")
        self._lbl_troco_rotulo.setObjectName("labelForm")
        col.addWidget(self._lbl_troco_rotulo)
        self._lbl_troco = QLabel("R$ 0,00")
        self._lbl_troco.setObjectName("valorDestaque")
        estado_sucesso(self._lbl_troco)
        col.addWidget(self._lbl_troco)
        return caixa

    def _montar_totais(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("cardLow")
        col = QVBoxLayout(caixa)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(6)

        linha = QHBoxLayout()
        rotulo = QLabel("Subtotal")
        estado_muted(rotulo)
        self._lbl_subtotal = QLabel("R$ 0,00")
        estado_muted(self._lbl_subtotal)
        linha.addWidget(rotulo)
        linha.addStretch(1)
        linha.addWidget(self._lbl_subtotal)
        col.addLayout(linha)

        linha_desc = QHBoxLayout()
        rotulo_desc = QLabel("Desconto")
        estado_muted(rotulo_desc)
        self._lbl_desconto_totais = QLabel("R$ 0,00")
        estado_muted(self._lbl_desconto_totais)
        linha_desc.addWidget(rotulo_desc)
        linha_desc.addStretch(1)
        linha_desc.addWidget(self._lbl_desconto_totais)
        col.addLayout(linha_desc)
        # (P2#12) O sinal negativo é setado em `_recalcular_totais`.

        linha2 = QHBoxLayout()
        rotulo2 = QLabel("Total")
        rotulo2.setStyleSheet("font-weight: 700;")
        self._lbl_total = QLabel("R$ 0,00")
        self._lbl_total.setObjectName("totalPdv")  # 28 px: hierarquia do total
        linha2.addWidget(rotulo2)
        linha2.addStretch(1)
        linha2.addWidget(self._lbl_total)
        col.addLayout(linha2)
        return caixa

    def _montar_acoes(self) -> QWidget:
        """Ações com o atalho DENTRO do botão (P2#13): nada de chips soltos.

        Esc NÃO descarta a venda às cegas: com itens em andamento pede
        confirmação (P0#4).
        """
        caixa = QWidget()
        caixa.setObjectName("caixaForma")
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)
        linha.addStretch(1)
        self._btn_cancelar = QPushButton("Cancelar (Esc)")
        estado_secundario(self._btn_cancelar)
        self._btn_cancelar.setToolTip("Descartar venda em andamento (Esc) — pede confirmação se houver itens")
        self._btn_salvar = QPushButton("Finalizar venda (F9)")
        estado_primario(self._btn_salvar)
        self._btn_salvar.setToolTip("Finalizar venda (F9)")
        self._btn_cancelar.clicked.connect(self._descartar_se_houver_itens)
        self._btn_salvar.clicked.connect(self._salvar)
        linha.addWidget(self._btn_cancelar)
        linha.addWidget(self._btn_salvar)
        return caixa

    def _descartar_se_houver_itens(self) -> None:
        """Esc/Cancelar não perdem a venda com um toque acidental (P0#4)."""
        if self._itens_editor.valor():
            resposta = QMessageBox.question(
                self,
                "Descartar venda",
                "Há itens na venda em andamento.\nDeseja realmente descartá-la?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        self._limpar_form()

    # ----------------------------------------------------- vista histórico

    def _montar_vista_historico(self) -> QWidget:
        pagina = QWidget()
        col = QVBoxLayout(pagina)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        barra = QWidget()
        barra.setObjectName("caixaForma")
        linha = QHBoxLayout(barra)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)

        self._busca = CampoBusca(self.LUGAR_BUSCA, nivel_hint="Ctrl+F")
        self._busca.buscado.connect(lambda q: self.recarregar(q))
        linha.addWidget(self._busca, 1)

        self._btn_filtros: dict[str, QPushButton] = {}
        for valor, rotulo in self.FILTROS:
            botao = QPushButton(rotulo)
            botao.setCheckable(True)
            botao.setObjectName("chaveRapida")
            if valor == "":
                botao.setChecked(True)
            botao.clicked.connect(lambda _=False, v=valor: self._aplicar_filtro(v))
            self._btn_filtros[valor] = botao
            linha.addWidget(botao)

        self._filtro_forma = ""
        self._combo_forma_hist = QComboBox()
        self._combo_forma_hist.addItem("Todas as formas", "")
        for v, r in FORMAS_PAGAMENTO:
            self._combo_forma_hist.addItem(r, v)
        self._combo_forma_hist.currentIndexChanged.connect(
            lambda: self._aplicar_filtro_forma(self._combo_forma_hist.currentData() or "")
        )
        linha.addWidget(self._combo_forma_hist)

        # P1#15 (parcial): filtros por período e operador.
        from PySide6.QtCore import QDate
        self._data_ini_hist = QDateEdit()
        self._data_ini_hist.setCalendarPopup(True)
        self._data_ini_hist.setDisplayFormat("dd/MM/yyyy")
        self._data_ini_hist.setSpecialValueText("De")
        self._data_ini_hist.setDate(QDate(2000, 1, 1))
        self._data_fim_hist = QDateEdit()
        self._data_fim_hist.setCalendarPopup(True)
        self._data_fim_hist.setDisplayFormat("dd/MM/yyyy")
        self._data_fim_hist.setSpecialValueText("Até")
        self._data_fim_hist.setDate(QDate(2000, 1, 1))
        for w in (self._data_ini_hist, self._data_fim_hist):
            w.setMinimumDate(QDate(2000, 1, 1))
            w.setMaximumDate(QDate(2100, 12, 31))
            w.dateChanged.connect(lambda *_: self.recarregar(self._busca.texto()))
        linha.addWidget(self._data_ini_hist)
        linha.addWidget(self._data_fim_hist)

        self._filtro_operador = None
        self._combo_operador_hist = QComboBox()
        self._combo_operador_hist.addItem("Todos operadores", None)
        self._combo_operador_hist.currentIndexChanged.connect(
            lambda: self._aplicar_filtro_operador(self._combo_operador_hist.currentData())
        )
        linha.addWidget(self._combo_operador_hist)
        # carrega operadores (usuarios) se permitido; falha silenciosa
        tarefas.rodar(
            lambda: self._api.listar("usuarios", limit=200),
            on_ok=self._operadores_recebidos,
            on_erro=lambda _m: None,
        )

        # Exportação pertence ao Histórico (P1#6), não ao cabeçalho do PDV.
        self._btn_exportar = QPushButton(self.ROTULO_EXPORTAR)
        self._btn_exportar.setEnabled(False)
        self._btn_exportar.clicked.connect(self._exportar)
        linha.addWidget(self._btn_exportar)

        btn_limpar = QPushButton("Limpar filtros")
        btn_limpar.setToolTip("Limpar busca, status, forma, operador e período")
        btn_limpar.clicked.connect(self._limpar_filtros_historico)
        linha.addWidget(btn_limpar)
        col.addWidget(barra)

        self._lbl_resumo_hist = QLabel("")
        self._lbl_resumo_hist.setObjectName("textoMuted")
        self._lbl_resumo_hist.setWordWrap(True)
        col.addWidget(self._lbl_resumo_hist)

        card = QWidget()
        card.setObjectName("card")
        col_card = QVBoxLayout(card)
        col_card.setContentsMargins(0, 0, 0, 0)
        col_card.setSpacing(0)

        self._tabela = TabelaDensa(self.CHAVES, self.COLUNAS)
        self._tabela.formata = self._formatar_texto
        self._tabela.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        cab = self._tabela.horizontalHeader()
        cab.setStretchLastSection(False)
        cab.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cab.setSectionResizeMode(
            self.CHAVES.index("cliente_nome"), QHeaderView.ResizeMode.Stretch
        )
        if "fiscal" in self.CHAVES:
            col_fiscal = self.CHAVES.index("fiscal")
            cab.setSectionResizeMode(col_fiscal, QHeaderView.ResizeMode.Fixed)
            self._tabela.setColumnWidth(col_fiscal, 70)
        # P0#3/P1#14: ações compactas (menu ⋯).
        col_acoes = self.CHAVES.index("acoes")
        cab.setSectionResizeMode(col_acoes, QHeaderView.ResizeMode.Fixed)
        self._tabela.setColumnWidth(col_acoes, 120)

        self._vazio = QLabel("Nenhuma venda encontrada. Clique em Nova venda (F6).")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        estado_muted(self._vazio)
        self._vazio.setWordWrap(True)

        self._pilha_lista = QStackedWidget()
        self._pilha_lista.addWidget(self._tabela)
        self._pilha_lista.addWidget(self._vazio)
        col_card.addWidget(self._pilha_lista, 1)

        linha_pag = QWidget()
        linha_pag.setObjectName("caixaForma")
        pag = QHBoxLayout(linha_pag)
        pag.setContentsMargins(14, 8, 14, 8)
        self._paginador = Paginador()
        self._paginador.mudou.connect(
            lambda offset: self.recarregar(self._busca.texto(), offset)
        )
        pag.addWidget(self._paginador)
        col_card.addWidget(linha_pag)

        col.addWidget(card, 1)
        return pagina

    # ----------------------------------------------------------- interação

    def _conectar_campos(self) -> None:
        self._cliente.widget.currentIndexChanged.connect(self._ao_mudar_cliente)
        self._forma.widget.currentIndexChanged.connect(self._forma_mudou)
        self._desconto.edicao.textChanged.connect(self._recalcular_totais)
        self._recebido.edicao.textChanged.connect(self._atualizar_troco)
        self._itens_editor.alterado.connect(self._recalcular_totais)

    def _ao_mudar_cliente(self) -> None:
        # Combo único e pesquisável (P1#9): o nome digitado que NÃO casar com
        # um cadastro é resolvido como cliente avulso no payload.
        self._cliente_mudou()

    def _clientes_flags_recebidos(self, saida: dict) -> None:
        super()._clientes_flags_recebidos(saida)
        # Completer do combo pesquisável aponta para o modelo atualizado (P1#9).
        self._completer_clientes.setModel(self._cliente.widget.model())
        self._completer_clientes.setCompletionRole(Qt.ItemDataRole.DisplayRole)

    def _forma_mudou(self) -> None:
        forma = self._forma.valor()
        parcelavel = forma in FORMAS_PAGAMENTO_PARCELAVEIS
        self._campo_parcelas.setVisible(parcelavel)
        dinheiro = forma == _FORMA_DINHEIRO
        self._campo_recebido.setVisible(dinheiro)
        self._campo_troco.setVisible(dinheiro)
        if not parcelavel:
            self._parcelas.definir("1")
        self._recalcular_totais()

    def _recalcular_totais(self) -> None:
        if not hasattr(self, "_lbl_total"):
            return
        subtotal = self._itens_editor.subtotal()
        desconto = _dec(self._desconto.valor())
        total = subtotal - desconto
        if total < 0:
            total = Decimal("0")
        self._total_venda = total
        self._lbl_subtotal.setText(formatar_moeda(str(subtotal)))
        # Desconto com sinal (P2#12): o efeito no total fica explícito.
        self._lbl_desconto_totais.setText(
            f"-{formatar_moeda(str(desconto))}" if desconto > 0 else formatar_moeda("0")
        )
        self._lbl_total.setText(formatar_moeda(str(total)))
        n = len(self._itens_editor.valor())
        # Itens + subtotal na mesma linha (P1#7).
        self._lbl_resumo_itens.setText(
            f"{n} {'item' if n == 1 else 'itens'} · subtotal {formatar_moeda(str(subtotal))}"
        )
        self._atualizar_troco()
        self._atualizar_estado_finalizar()

    def _atualizar_troco(self) -> None:
        if not hasattr(self, "_lbl_troco"):
            return
        recebido = _dec(self._recebido.valor())
        troco = recebido - self._total_venda
        if recebido > 0 and troco < 0:
            # Dinheiro entregue não cobre o total: aviso claro.
            self._lbl_troco_rotulo.setText("FALTA")
            self._lbl_troco.setText(formatar_moeda(str(-troco)))
            estado_atencao(self._lbl_troco)
        else:
            self._lbl_troco_rotulo.setText("TROCO")
            self._lbl_troco.setText(formatar_moeda(str(troco if troco > 0 else 0)))
            estado_sucesso(self._lbl_troco)
        # P0#6 (revisão PDV+Hist+OS): em dinheiro, recebido >= total implica
        # pagamento concluído no ato — reflete no indicador de confirmação.
        if self._forma.valor() == _FORMA_DINHEIRO and recebido > 0 and troco >= 0 and self._total_venda > 0:
            self._pagamento_confirmado.definir(True)
        aplicar_estilo(self._lbl_troco)

    def _atualizar_estado_finalizar(self) -> None:
        """Finalizar desabilitado SEMPRE com o motivo explícito (P0#5)."""
        if not hasattr(self, "_btn_salvar"):
            return
        n = len(self._itens_editor.valor())
        if self._modo_leitura:
            self._btn_salvar.setEnabled(False)
            self._btn_salvar.setToolTip("Modo leitura: venda bloqueada pela licença")
        elif getattr(self, "_caixa_fechado", False):
            self._btn_salvar.setEnabled(False)
            self._btn_salvar.setToolTip("Abra o caixa para registrar vendas")
        elif n == 0:
            self._btn_salvar.setEnabled(False)
            self._btn_salvar.setToolTip("Adicione ao menos 1 item")
        else:
            self._btn_salvar.setEnabled(True)
            self._btn_salvar.setToolTip("Finalizar venda (F9)")

    def _limpar_form(self) -> None:
        self._itens_editor.limpar()
        self._cliente.definir(None)
        # Combo editável: volta ao padrão "Consumidor final" no texto também.
        if self._cliente.widget.isEditable():
            self._cliente.widget.setEditText("Consumidor final")
        self._vendedor.definir(None)
        self._forma.definir(_FORMA_DINHEIRO)
        self._parcelas.definir("1")
        self._recebido.definir(None)
        self._desconto.definir(None)
        self._pagamento_confirmado.definir(False)
        self._nfce.definir(False)
        self._forma_mudou()
        self._ao_mudar_cliente()

    # ------------------------------------------------------------- abas

    def _ir_para_venda(self) -> None:
        self._vistas.setCurrentIndex(0)
        if hasattr(self, "_botao_venda"):
            self._botao_venda.setChecked(True)
        self._botao_historico.setChecked(False)
        self._verificar_caixa()

    def _ir_para_historico(self) -> None:
        self._vistas.setCurrentIndex(1)
        if hasattr(self, "_botao_venda"):
            self._botao_venda.setChecked(False)
        self._botao_historico.setChecked(True)
        self._busca.focar()

    # ------------------------------------------------------------ busca

    def _aplicar_filtro(self, valor: str) -> None:
        self._filtro = valor
        for v, botao in self._btn_filtros.items():
            botao.setChecked(v == valor)
        self.recarregar(self._busca.texto())

    def _aplicar_filtro_forma(self, valor: str) -> None:
        self._filtro_forma = valor or ""
        self.recarregar(self._busca.texto())

    def _aplicar_filtro_operador(self, valor) -> None:
        self._filtro_operador = valor
        self.recarregar(self._busca.texto())

    def _operadores_recebidos(self, saida: dict) -> None:
        if not hasattr(self, "_combo_operador_hist"):
            return
        atual = self._combo_operador_hist.currentData()
        self._combo_operador_hist.blockSignals(True)
        self._combo_operador_hist.clear()
        self._combo_operador_hist.addItem("Todos operadores", None)
        for u in saida.get("data", []):
            nome = u.get("nome") or u.get("login") or str(u.get("id"))
            self._combo_operador_hist.addItem(str(nome), u.get("id"))
        idx = self._combo_operador_hist.findData(atual)
        self._combo_operador_hist.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_operador_hist.blockSignals(False)

    def _limpar_filtros_historico(self) -> None:
        from PySide6.QtCore import QDate

        if hasattr(self, "_busca"):
            self._busca.definir("")
        self._aplicar_filtro("ok")
        if hasattr(self, "_combo_forma_hist"):
            self._combo_forma_hist.blockSignals(True)
            self._combo_forma_hist.setCurrentIndex(0)
            self._combo_forma_hist.blockSignals(False)
            self._filtro_forma = ""
        if hasattr(self, "_combo_operador_hist"):
            self._combo_operador_hist.blockSignals(True)
            self._combo_operador_hist.setCurrentIndex(0)
            self._combo_operador_hist.blockSignals(False)
            self._filtro_operador = None
        if hasattr(self, "_data_ini_hist"):
            self._data_ini_hist.blockSignals(True)
            self._data_ini_hist.setDate(QDate(2000, 1, 1))
            self._data_ini_hist.blockSignals(False)
        if hasattr(self, "_data_fim_hist"):
            self._data_fim_hist.blockSignals(True)
            self._data_fim_hist.setDate(QDate(2000, 1, 1))
            self._data_fim_hist.blockSignals(False)
        self.recarregar("")

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        data_inicio = None
        data_fim = None
        if hasattr(self, "_data_ini_hist"):
            d = self._data_ini_hist.date()
            if d.isValid() and d.year() > 2000:
                data_inicio = d.toString("yyyy-MM-dd")
        if hasattr(self, "_data_fim_hist"):
            d = self._data_fim_hist.date()
            if d.isValid() and d.year() > 2000:
                data_fim = d.toString("yyyy-MM-dd")
        return self._api.listar_vendas(
            q=q,
            status_venda=self._filtro or None,
            forma_pagamento=(self._filtro_forma or None) if hasattr(self, "_filtro_forma") else None,
            operador_id=(self._filtro_operador if hasattr(self, "_filtro_operador") else None),
            data_inicio=data_inicio,
            data_fim=data_fim,
            limit=LOTE,
            offset=offset,
        )

    def recarregar(self, q: str = "", offset: int | None = None) -> None:
        if offset is None:
            offset = self._offset
        self._seq += 1
        seq = self._seq

        def _receber(saida: dict) -> None:
            if seq != self._seq:
                return
            self._recebidos(saida, offset)

        self._tabela.carregando(True)
        tarefas.rodar(
            lambda: self._listar(q, offset, {}),
            on_ok=_receber,
            on_erro=self._erro_carga,
        )

    def _recebidos(self, saida: dict, offset: int) -> None:
        self._linhas = saida["data"]
        self._total = saida["total"]
        self._offset = offset
        self._tabela.preencher(self._linhas)
        self._paginador.atualizar(self._total, offset, LOTE)
        self._montar_acoes_linhas()
        self._atualizar_resumo_historico()
        self._atualizar_resumo_consolidado(self._busca.texto() if hasattr(self, "_busca") else "")
        self._pilha_lista.setCurrentWidget(
            self._tabela if self._total else self._vazio
        )
        self._btn_exportar.setEnabled(self._total > 0)

    def _atualizar_resumo_historico(self) -> None:
        if not hasattr(self, "_lbl_resumo_hist"):
            return
        totais: dict[str, Decimal] = {}
        qtd_ok = 0
        for v in self._linhas:
            if str(v.get("status")) != "ok":
                continue
            qtd_ok += 1
            forma = str(v.get("forma_pagamento") or "")
            totais[forma] = totais.get(forma, Decimal("0")) + _dec(v.get("valor_total"))
        if not totais:
            self._lbl_resumo_hist.setText("Resumo (página): sem vendas finalizadas.")
            return
        partes = []
        for forma, rot in FORMAS_PAGAMENTO:
            if forma in totais:
                partes.append(f"{rot}: {formatar_moeda(str(totais[forma]))}")
        for forma, val in totais.items():
            if forma not in dict(FORMAS_PAGAMENTO):
                partes.append(f"{forma}: {formatar_moeda(str(val))}")
        self._lbl_resumo_hist.setText(
            "Resumo (página, finalizadas): " + " · ".join(partes) + f" · Vendas: {qtd_ok}"
        )

    def _atualizar_resumo_consolidado(self, q: str = "") -> None:
        if not hasattr(self, "_lbl_resumo_hist"):
            return
        # Consolidado respeita os mesmos filtros selecionados.
        data_inicio = None
        data_fim = None
        if hasattr(self, "_data_ini_hist"):
            d = self._data_ini_hist.date()
            if d.isValid() and d.year() > 2000:
                data_inicio = d.toString("yyyy-MM-dd")
        if hasattr(self, "_data_fim_hist"):
            d = self._data_fim_hist.date()
            if d.isValid() and d.year() > 2000:
                data_fim = d.toString("yyyy-MM-dd")
        status_venda = self._filtro or None

        def _ok(resp: dict) -> None:
            if not hasattr(self, "_lbl_resumo_hist"):
                return
            data = resp.get("data", resp) if isinstance(resp, dict) else {}
            por_forma = data.get("por_forma") or []
            qtd = data.get("quantidade", 0)
            total = data.get("total", 0)
            if not por_forma and not qtd:
                return
            partes = []
            mapa = {f: r for f, r in FORMAS_PAGAMENTO}
            for item in por_forma:
                forma = str(item.get("forma_pagamento") or "")
                rot = mapa.get(forma, forma.upper())
                partes.append(f"{rot}: {formatar_moeda(str(item.get('total') or 0))}")
            escopo = "filtro"
            if status_venda == "ok":
                escopo = "filtro, finalizadas"
            elif status_venda == "cancelado":
                escopo = "filtro, canceladas"
            elif status_venda is None:
                escopo = "filtro, todas"
            texto = f"Resumo ({escopo}): " + (" · ".join(partes) if partes else formatar_moeda(str(total)))
            texto += f" · Vendas: {qtd} · Total: {formatar_moeda(str(total))}"
            self._lbl_resumo_hist.setText(texto)

        tarefas.rodar(
            lambda: self._api.resumo_vendas(
                q=q,
                status_venda=status_venda,
                forma_pagamento=(self._filtro_forma or None) if hasattr(self, "_filtro_forma") else None,
                operador_id=(self._filtro_operador if hasattr(self, "_filtro_operador") else None),
                data_inicio=data_inicio,
                data_fim=data_fim,
            ),
            on_ok=_ok,
            on_erro=lambda _m: None,
        )

    def _erro_carga(self, msg: str) -> None:
        self._tabela.limpar()
        self._vazio.setText(f"Não foi possível carregar as vendas: {msg}")
        self._pilha_lista.setCurrentWidget(self._vazio)
        self._btn_exportar.setEnabled(False)
        QMessageBox.warning(self, "Local API Service", msg)

    def _montar_acoes_linhas(self) -> None:
        coluna = self.CHAVES.index("acoes")
        col_num = self.CHAVES.index("numero")
        col_total = self.CHAVES.index("valor_total")
        col_data = self.CHAVES.index("data_venda")
        col_fiscal = self.CHAVES.index("fiscal") if "fiscal" in self.CHAVES else -1
        for linha, dado in enumerate(self._linhas):
            caixa = QWidget()
            h = QHBoxLayout(caixa)
            h.setContentsMargins(6, 4, 6, 4)
            h.setSpacing(6)
            # P1#14: ação principal visível + ações secundárias agrupadas em ⋯
            btn_ver = QPushButton("Ver")
            btn_ver.setObjectName("acaoLinha")
            btn_ver.setMinimumHeight(30)
            btn_ver.clicked.connect(
                lambda _=False, vid=dado.get("id"): self._ver_detalhes(vid)
            )
            h.addWidget(btn_ver)
            btn_mais = QToolButton()
            btn_mais.setText("⋯")
            btn_mais.setObjectName("acaoLinha")
            btn_mais.setMinimumHeight(30)
            btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(btn_mais)
            act_ver = menu.addAction("Ver detalhes")
            act_ver.triggered.connect(lambda _=False, vid=dado.get("id"): self._ver_detalhes(vid))
            if dado.get("status") == "ok" and not self._modo_leitura:
                act_cancelar = menu.addAction("Cancelar venda")
                act_cancelar.triggered.connect(lambda _=False, alvo=dado: self._cancelar_venda(alvo))
            btn_mais.setMenu(menu)
            h.addWidget(btn_mais)
            h.addStretch(1)
            self._tabela.setCellWidget(linha, coluna, caixa)
            # P1#13/#14: valores/datas alinhados à direita; fiscal centralizado.
            for c in (col_num, col_total, col_data):
                item = self._tabela.item(linha, c)
                if item is not None:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
            if col_fiscal >= 0:
                item = self._tabela.item(linha, col_fiscal)
                if item is not None:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            for c in range(len(self.CHAVES)):
                item = self._tabela.item(linha, c)
                if item is not None:
                    dica = item.text()
                    if c == self.CHAVES.index("status") and str(dado.get("status")) == "cancelado":
                        motivo = (dado.get("motivo_cancelamento") or "").strip()
                        if motivo:
                            dica = f"{dica}\nMotivo: {motivo}"
                    item.setToolTip(dica)

    def _ver_detalhes(self, venda_id) -> None:
        if venda_id is None:
            return

        def ok(dado: dict) -> None:
            venda = dado.get("data", dado) if isinstance(dado, dict) else dado
            self._mostrar_dialogo_detalhes(venda)

        def erro(msg: str) -> None:
            QMessageBox.warning(self, "Venda", msg)

        tarefas.rodar(lambda: self._api.obter("vendas", venda_id), on_ok=ok, on_erro=erro)

    def _mostrar_dialogo_detalhes(self, venda: dict) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Venda Nº {venda.get('numero', '')}")
        dlg.resize(760, 520)
        layout = QVBoxLayout(dlg)

        grade = QGridLayout()
        campos = [
            ("Data", formatar_data_iso(venda.get("data_venda"))),
            ("Cliente", venda.get("cliente_nome") or "Consumidor final"),
            ("Vendedor", venda.get("vendedor_nome") or "—"),
            ("Operador", venda.get("operador_caixa_nome") or "—"),
            ("Status", _ROTULO_STATUS.get(str(venda.get("status") or ""), str(venda.get("status") or ""))),
            ("Pagamento", _ROTULO_PAGAMENTO.get(str(venda.get("forma_pagamento") or ""), str(venda.get("forma_pagamento") or ""))),
            ("Parcelas", str(venda.get("parcelas") or 1)),
            ("Valor itens", formatar_moeda(venda.get("valor_itens"))),
            ("Desconto", formatar_moeda(venda.get("desconto"))),
            ("Total", formatar_moeda(venda.get("valor_total"))),
            ("Valor recebido", formatar_moeda(venda.get("valor_recebido")) if venda.get("valor_recebido") is not None else "—"),
            ("Troco", formatar_moeda(venda.get("troco")) if venda.get("troco") is not None else "—"),
        ]
        if str(venda.get("status") or "") == "cancelado":
            cancelado_em = venda.get("cancelado_em")
            if cancelado_em:
                cancelado_em = str(cancelado_em).replace("T", " ")[:16]
            campos.extend([
                ("Cancelado em", cancelado_em or "—"),
                ("Motivo cancelamento", venda.get("motivo_cancelamento") or "—"),
            ])
        for i, (rotulo, valor) in enumerate(campos):
            lbl_r = QLabel(f"<b>{rotulo}:</b>")
            lbl_v = QLabel(str(valor))
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grade.addWidget(lbl_r, i // 2, (i % 2) * 2)
            grade.addWidget(lbl_v, i // 2, (i % 2) * 2 + 1)
        layout.addLayout(grade)

        obs = venda.get("observacoes")
        if obs:
            lbl_obs = QLabel(f"<b>Observações:</b> {obs}")
            lbl_obs.setWordWrap(True)
            layout.addWidget(lbl_obs)

        lbl_itens = QLabel("<b>Itens / produtos vendidos</b>")
        layout.addWidget(lbl_itens)
        tabela = QTableWidget(0, 5)
        tabela.setHorizontalHeaderLabels(["Descrição", "Qtd", "Valor unit.", "Desconto", "Total"])
        tabela.verticalHeader().setVisible(False)
        tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cab = tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            cab.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        itens = venda.get("itens") or []
        tabela.setRowCount(len(itens))
        produtos = getattr(self._itens_editor, "_produtos", {}) or {}
        for r, it in enumerate(itens):
            pid = it.get("produto_id")
            nome_prod = (produtos.get(pid) or {}).get("nome") if pid else None
            desc = (
                it.get("descricao_avulsa")
                or nome_prod
                or (f"Produto #{pid}" if pid else "—")
            )
            vals = [
                str(desc),
                _texto_numero(it.get("quantidade")),
                formatar_moeda(it.get("valor_unitario")),
                formatar_moeda(it.get("desconto")),
                formatar_moeda(it.get("valor_total")),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela.setItem(r, c, item)
        layout.addWidget(tabela, 1)

        btn = QPushButton("Fechar")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()

    def _cancelar_venda(self, dado: dict, motivo: str | None = None) -> None:
        if motivo is None:
            motivo_informado, ok = QInputDialog.getMultiLineText(
                self,
                "Cancelar venda",
                f"Informe o motivo do cancelamento da venda Nº {dado.get('numero')}:",
                "",
            )
            if not ok:
                return
            motivo = (motivo_informado or "").strip() or None
        resposta = QMessageBox.question(
            self,
            "Cancelar venda",
            f"Cancelar a venda Nº {dado.get('numero')}?\n\n"
            "Ação sensível: pode impactar caixa/estoque conforme regras do sistema. "
            "Confirme apenas se tiver certeza.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        payload = {"motivo": motivo} if motivo else None
        tarefas.rodar(
            lambda: self._api.excluir("vendas", dado["id"], payload=payload),
            on_ok=lambda _out: self.recarregar(self._busca.texto()),
            on_erro=lambda msg: QMessageBox.warning(self, "Cancelar venda", msg),
        )

    # ------------------------------------------------------------ salvar

    def _validar(self):
        if not self._forma.valor():
            return ("Informe a forma de pagamento.", self._forma)
        if self._forma.valor() in FORMAS_PAGAMENTO_PARCELAVEIS:
            parcelas = (self._parcelas.valor() or "").strip()
            if not parcelas.isdigit() or int(parcelas) < 1:
                return ("Parcelas deve ser um número maior que zero.", self._parcelas)
        if not self._itens_editor.valor():
            return ("Adicione ao menos um item à venda.", self._itens_editor)
        exigencia = self._exigencia_pendente()
        if exigencia:
            return (
                f"O cliente exige {exigencia}. Marque 'Adiantamento/sinal já "
                "recebido' para finalizar a venda.",
                self._pagamento_confirmado,
            )
        return None

    def _cliente_do_combo(self) -> tuple[int | None, str | None]:
        """Resolve o campo único de cliente (P1#9).

        Texto que casa exatamente com um cadastro → `cliente_id`; texto livre
        (≠ "Consumidor final") → `cliente_nome_avulso`; vazio → (None, None).
        """
        texto = self._cliente.widget.currentText().strip()
        if not texto or texto.casefold() == "consumidor final":
            return None, None
        combo = self._cliente.widget
        for i in range(combo.count()):
            rotulo = str(combo.itemText(i) or "").strip()
            if rotulo and rotulo.casefold() == texto.casefold():
                return combo.itemData(i), None
        return None, texto

    def _payload(self) -> dict:
        forma = self._forma.valor()
        if forma in FORMAS_PAGAMENTO_PARCELAVEIS:
            parcelas = int((self._parcelas.valor() or "1").strip() or "1")
        else:
            parcelas = 1
        cliente_id, cliente_avulso = self._cliente_do_combo()
        payload = {
            "cliente_id": cliente_id,
            "cliente_nome_avulso": cliente_avulso,
            "vendedor_id": self._vendedor.valor(),
            "desconto": str(_dec(self._desconto.valor())),
            "forma_pagamento": forma,
            "parcelas": parcelas,
            "pagamento_confirmado": self._pagamento_confirmado.valor(),
            "itens": self._itens_editor.valor(),
        }
        if forma == _FORMA_DINHEIRO:
            recebido = _dec(self._recebido.valor())
            if recebido > 0:
                payload["valor_recebido"] = str(recebido)
                troco = recebido - self._total_venda
                payload["troco"] = str(troco if troco > 0 else Decimal("0"))
        return payload

    def _salvar(self) -> None:
        if self._modo_leitura:
            return
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            if getattr(campo, "widget", None) is not None:
                campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)
        emitir_nfce = self._nfce.valor()
        tarefas.rodar(
            lambda: self._api.criar("vendas", self._payload()),
            on_ok=lambda dado: self._salvo(dado, emitir_nfce),
            on_erro=self._erro_salvar,
        )

    def _salvo(self, dado: dict, emitir_nfce: bool) -> None:
        self._btn_salvar.setEnabled(True)
        catalogos.invalidar("vendas")
        numero = (dado or {}).get("numero")
        self._limpar_form()
        self.recarregar(self._busca.texto())
        if emitir_nfce:
            QMessageBox.information(
                self,
                "NFC-e",
                f"Venda Nº {numero} registrada.\n"
                "A emissão de NFC-e estará disponível em uma próxima etapa.",
            )

    def _erro_salvar(self, msg: str) -> None:
        self._btn_salvar.setEnabled(True)
        QMessageBox.critical(self, "Não foi possível finalizar a venda", msg)

    # ------------------------------------------------------------ tabela

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "acoes":
            return ""
        if chave == "numero":
            numero = dado.get("numero")
            return "" if numero is None else str(numero)
        if chave == "data_venda":
            valor = dado.get("data_venda")
            texto = formatar_data_iso(valor)
            bruto = str(valor or "")
            # Se vier ISO com horário, exibe data + hora (P1#14).
            if "T" in bruto and len(bruto) >= 16:
                hora = bruto[11:16]
                return f"{texto} {hora}" if texto else hora
            return texto
        if chave == "cliente_nome":
            return dado.get("cliente_nome") or "Consumidor final"
        if chave == "forma_pagamento":
            valor = str(dado.get("forma_pagamento") or "")
            return _ROTULO_PAGAMENTO.get(valor, valor.upper())
        if chave == "valor_total":
            return formatar_moeda(dado.get("valor_total"))
        if chave == "status":
            valor = str(dado.get("status") or "")
            rotulo = _ROTULO_STATUS.get(valor, valor.upper())
            if valor == "ok":
                return f"● {rotulo}"
            if valor == "cancelado":
                return f"○ {rotulo}"
            return rotulo
        if chave == "fiscal":
            # NFC-e/fiscal: não implementado neste módulo; exibe estado neutro.
            return "—"
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    def _exportar(self) -> None:
        QMessageBox.information(
            self,
            self.ROTULO_EXPORTAR,
            "Exportação para planilha estará disponível na próxima etapa.",
        )

    # ------------------------------------------------------- modo leitura

    def _aplicar_modo_leitura(self) -> None:
        ligado = not self._modo_leitura
        self._btn_cancelar.setEnabled(ligado)
        for campo in (
            self._cliente,
            self._vendedor,
            self._forma,
            self._parcelas,
            self._recebido,
            self._desconto,
            self._pagamento_confirmado,
            self._nfce,
        ):
            campo.habilitar(ligado)
        self._itens_editor.habilitar(ligado)
        self._atualizar_estado_finalizar()

    # ------------------------------------------------------------ atalhos

    def _instalar_atalhos(self) -> None:
        # Atalhos da página ficam restritos à própria página (foco dentro dela):
        # assim F6/F9/Esc não disparam enquanto outra tela está ativa.
        atalho_nova = QShortcut(QKeySequence("F6"), self)
        atalho_nova.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho_nova.activated.connect(self._ir_para_venda)

        atalho_finalizar = QShortcut(QKeySequence("F9"), self)
        atalho_finalizar.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho_finalizar.activated.connect(self._salvar)

        # Esc pergunta antes de descartar uma venda com itens (P0#4).
        atalho_esc = QShortcut(QKeySequence("Esc"), self)
        atalho_esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho_esc.activated.connect(self._descartar_se_houver_itens)

        # Ctrl+F foca a busca da visão ativa: na venda, resta ao widget da vista
        # (WidgetWithChildrenShortcut); no histórico, o próprio `CampoBusca`.
        atalho = QShortcut(QKeySequence("Ctrl+F"), self._vista_venda)
        atalho.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho.activated.connect(self._itens_editor.focar_busca)

    # ------------------------------------------------------- carregar aux

    def _carregar_vendedores(self) -> None:
        catalogos.carregar(
            "funcionarios",
            lambda: self._api.listar("funcionarios", limit=1000),
            on_ok=self._vendedores_recebidos,
        )

    def _vendedores_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        vendedores = [r for r in dados if r.get("e_vendedor")] or dados
        self._vendedor.alterar_opcoes(
            [(r["id"], r["nome"]) for r in vendedores]
        )

    def _montar_banner_caixa(self) -> QWidget:
        """Estado do caixa no topo do PDV (P0#3).

        Fechado: banner de aviso com **Abrir caixa** como botão PRIMÁRIO ao
        lado do texto (abre modal com valor de troco). Aberto: chip discreto
        "Caixa aberto · desde HH:MM".
        """
        self._banner_caixa = QWidget()
        self._banner_caixa.setObjectName("bannerAviso")
        linha = QHBoxLayout(self._banner_caixa)
        linha.setContentsMargins(12, 8, 12, 8)
        linha.setSpacing(10)
        self._lbl_estado_caixa = QLabel(
            "Caixa fechado — abra o caixa antes de registrar vendas."
        )
        estado_atencao(self._lbl_estado_caixa)
        linha.addWidget(self._lbl_estado_caixa, 1)
        self._btn_abrir_caixa = QPushButton("Abrir caixa")
        estado_primario(self._btn_abrir_caixa)
        self._btn_abrir_caixa.clicked.connect(self._abrir_caixa_modal)
        linha.addWidget(self._btn_abrir_caixa)
        self._banner_caixa.setVisible(False)
        return self._banner_caixa

    def _abrir_caixa_modal(self) -> None:
        """Abre o caixa sem sair do PDV: modal com valor inicial (troco)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Abrir caixa")
        dlg.setMinimumWidth(360)
        col = QVBoxLayout(dlg)
        aviso = QLabel(
            "Informe o valor inicial de troco no gaveta. O caixa fica aberto "
            "para o seu usuário até o fechamento (manual ou automático às 23:00)."
        )
        aviso.setWordWrap(True)
        col.addWidget(aviso)
        campo = CampoValor("Valor inicial (troco)")
        campo.definir("0")
        col.addWidget(em_volta(campo))
        linha = QHBoxLayout()
        linha.addStretch(1)
        btn_cancelar = QPushButton("Cancelar")
        estado_secundario(btn_cancelar)
        btn_cancelar.clicked.connect(dlg.reject)
        btn_abrir = QPushButton("Abrir caixa")
        estado_primario(btn_abrir)
        btn_abrir.clicked.connect(dlg.accept)
        linha.addWidget(btn_cancelar)
        linha.addWidget(btn_abrir)
        col.addLayout(linha)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def ok(_saida) -> None:
            QMessageBox.information(
                self, "Caixa aberto", "Caixa aberto — bom trabalho!"
            )
            self._verificar_caixa()

        def erro(msg: str) -> None:
            QMessageBox.warning(self, "Abrir caixa", msg)

        tarefas.rodar(
            lambda: self._api.abrir_caixa(
                {
                    "valor_abertura": str(_dec(campo.valor())),
                    "observacoes": limpo("Aberto pelo PDV"),
                }
            ),
            on_ok=ok,
            on_erro=erro,
        )

    def _verificar_caixa(self) -> None:
        """Consulta o caixa do vendedor logado; `None` = fechado → bloqueia."""
        if self._modo_leitura or not self._api.autenticado:
            return

        def ok(caixa) -> None:
            fechado = caixa is None
            self._banner_caixa.setVisible(fechado)
            if fechado:
                self._lbl_estado_caixa.setText(
                    "Caixa fechado — abra o caixa antes de registrar vendas."
                )
            else:
                abertura = (caixa or {}).get("data_abertura") or ""
                desde = str(abertura)[11:16] if len(str(abertura)) >= 16 else ""
                self._lbl_estado_caixa.setText(
                    f"Caixa aberto{f' · desde {desde}' if desde else ''}"
                )
                self._lbl_estado_caixa.setProperty("badgeStyle", "success")
                aplicar_estilo(self._lbl_estado_caixa)
            self._aplicar_bloqueio_caixa(fechado)

        def erro(_msg) -> None:
            # Sem resposta do daemon: o estado fica como está — quem bloqueia
            # é o servidor (409 com a mensagem clara no Finalizar).
            pass

        tarefas.rodar(self._api.caixa_atual, ok, erro)

    def _aplicar_bloqueio_caixa(self, fechado: bool) -> None:
        """Caixa fechado bloqueia a venda INTEIRA (P0#3), não só o Finalizar."""
        self._caixa_fechado = fechado
        ligado = not fechado and not self._modo_leitura
        self._itens_editor.habilitar(ligado)
        for campo in (
            self._cliente,
            self._vendedor,
            self._forma,
            self._parcelas,
            self._recebido,
            self._desconto,
            self._pagamento_confirmado,
            self._nfce,
        ):
            campo.habilitar(ligado)
        self._atualizar_estado_finalizar()
        if not fechado and self._vistas.currentIndex() == 0:
            self._itens_editor.focar_busca()

    def showEvent(self, evento) -> None:  # noqa: N802 (API do Qt)
        super().showEvent(evento)
        self._verificar_caixa()
        # Foco na busca só com caixa aberto (P0#3: fechado, o foco não deve
        # sugerir digitar numa venda bloqueada).
        if (
            self._vistas.currentIndex() == 0
            and not self._modo_leitura
            and not self._caixa_fechado
        ):
            self._itens_editor.focar_busca()
