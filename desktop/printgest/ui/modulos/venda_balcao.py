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
    QCompleter,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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
    formatar_data_iso,
    formatar_moeda,
    para_decimal,
)
from printgest.ui.modulos.condicao_pagamento import CondicaoPagamentoCliente
from printgest.ui.paginador import LOTE, Paginador
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import aplicar_estilo, botao_com_atalho

# Formas que aceitam parcelamento (mostram o campo "Parcelas").
_FORMAS_PARCELAVEIS = {"cartao_credito", "boleto", "fiado"}
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
    """Rótulo acima do campo (padrão dos formulários do sistema)."""
    caixa = QWidget()
    caixa.setObjectName("caixaForma")  # fundo transparente: sem faixa cinza
    col = QVBoxLayout(caixa)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    label = QLabel(rotulo.upper())
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
        self._pilha_itens = QStackedWidget()
        self._pilha_itens.addWidget(self._tabela_itens())
        self._pilha_itens.addWidget(self._estado_vazio_itens())
        col.addWidget(self._pilha_itens, 1)

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
        self._qtd_add.setFixedWidth(56)
        linha.addWidget(self._qtd_add)

        self._btn_adicionar = QPushButton("Adicionar")
        self._btn_adicionar.setProperty("role", "primary")
        self._btn_adicionar.clicked.connect(self._adicionar_pela_busca)
        linha.addWidget(self._btn_adicionar)

        self._btn_avulso = QPushButton("Item avulso")
        self._btn_avulso.setToolTip(
            "Adiciona um item sem produto, usando o texto digitado como descrição"
        )
        self._btn_avulso.clicked.connect(self._adicionar_avulso)
        linha.addWidget(self._btn_avulso)
        return caixa

    def _estado_vazio_itens(self) -> QWidget:
        """Sem itens: orientação no lugar do vazio de ~600 px (revisão nº 1)."""
        caixa = QWidget()
        col = QVBoxLayout(caixa)
        col.setContentsMargins(0, 0, 0, 0)
        col.addStretch(2)
        titulo = QLabel("Busque um produto ou serviço para adicionar")
        titulo.setObjectName("vazioTabela")
        titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(titulo, 0, Qt.AlignmentFlag.AlignHCenter)
        dica = QLabel("Ctrl+F busca · F9 finaliza a venda · Esc descarta tudo")
        dica.setObjectName("vazioTabela")
        dica.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(dica, 0, Qt.AlignmentFlag.AlignHCenter)
        avulso = QLabel("Sem produto? Use “Item avulso” para lançar uma descrição livre.")
        avulso.setObjectName("vazioTabela")
        avulso.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(avulso, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(3)
        return caixa

    def _tabela_itens(self) -> QTableWidget:
        self._tabela = QTableWidget(0, len(self._CABECALHOS))
        self._tabela.setHorizontalHeaderLabels(self._CABECALHOS)
        self._tabela.verticalHeader().setVisible(False)
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
        # Estado vazio da lista: orientação no lugar do branco (revisão nº 1).
        self._pilha_itens.setCurrentIndex(0 if self._itens else 1)
        self._recalcular()

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
        "acoes",
    ]
    COLUNAS = ["Nº", "Data", "Cliente", "Pagamento", "Total", "Status", "Ações"]
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

        if self._nivel is not None and not pode_abrir(self._nivel, "os"):
            self._btn_nova_os.hide()

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
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)

        titulo = QLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        linha.addWidget(titulo)
        linha.addStretch(1)

        self._botao_venda = QPushButton("Nova venda")
        self._botao_venda.setCheckable(True)
        self._botao_venda.setObjectName("chaveRapida")
        self._botao_venda.setChecked(True)
        self._botao_venda.setToolTip("Nova venda (F6)")
        self._botao_venda.clicked.connect(self._ir_para_venda)
        linha.addWidget(self._botao_venda)

        self._botao_historico = QPushButton("Histórico")
        self._botao_historico.setCheckable(True)
        self._botao_historico.setObjectName("chaveRapida")
        self._botao_historico.setToolTip("Histórico de vendas")
        self._botao_historico.clicked.connect(self._ir_para_historico)
        linha.addWidget(self._botao_historico)

        linha.addSpacing(6)
        self._btn_nova_os = QPushButton("Nova OS/Orçamento")
        self._btn_nova_os.clicked.connect(lambda: self.navegar.emit("os"))
        linha.addWidget(self._btn_nova_os)

        self._btn_exportar = QPushButton(self.ROTULO_EXPORTAR)
        self._btn_exportar.setEnabled(False)
        self._btn_exportar.clicked.connect(self._exportar)
        linha.addWidget(self._btn_exportar)
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
        self._lbl_resumo_itens.setProperty("role", "muted")
        h.addWidget(self._lbl_resumo_itens)
        col_e.addWidget(cabeca)

        self._itens_editor = EditorItensVenda(api=self._api)
        col_e.addWidget(self._itens_editor, 1)
        linha.addWidget(esquerda, 3)

        # Coluna direita (~40%, mínimo 360): pagamento e totais, sem rolagem.
        direita = QWidget()
        direita.setObjectName("card")
        direita.setMinimumWidth(360)
        col_d = QVBoxLayout(direita)
        col_d.setContentsMargins(16, 14, 16, 14)
        col_d.setSpacing(12)

        titulo_pag = QLabel("PAGAMENTO")
        titulo_pag.setObjectName("labelForm")
        col_d.addWidget(titulo_pag)

        self._cliente = CampoCombo("Cliente", [(None, "Consumidor final")])
        self._vendedor = CampoCombo("Vendedor", [])
        self._vendedor.widget.setPlaceholderText("Selecione o vendedor")
        self._vendedor.widget.setCurrentIndex(-1)
        self._forma = CampoCombo("Forma de pagamento", FORMAS_PAGAMENTO)
        self._parcelas = CampoTexto("Parcelas", valor="1", maximo=2)
        self._recebido = CampoValor("Valor recebido")
        self._desconto = CampoValor("Desconto")

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
        grade.setHorizontalSpacing(16)
        grade.setVerticalSpacing(12)
        grade.addWidget(self._campo_cliente, 0, 0, 1, 2)
        grade.addWidget(self._campo_vendedor, 1, 0, 1, 2)
        grade.addWidget(self._campo_forma, 2, 0)
        grade.addWidget(self._campo_parcelas, 2, 1)
        grade.addWidget(self._campo_recebido, 3, 0)
        grade.addWidget(self._campo_troco, 3, 1)
        grade.addWidget(self._campo_desconto, 4, 0)
        grade.setColumnStretch(0, 1)
        grade.setColumnStretch(1, 1)
        col_d.addLayout(grade)

        self._pagamento_confirmado = CampoCheck("Pagamento já recebido")
        col_d.addWidget(self._pagamento_confirmado.widget)
        self._nfce = CampoCheck("Emitir NFC-e ao finalizar")
        col_d.addWidget(self._nfce.widget)

        # Resumo colado à barra de ações (revisão nº 7): o total é o dado mais
        # importante da tela e fica imediatamente acima do botão primário.
        col_d.addStretch(1)
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
        self._lbl_troco.setProperty("role", "success")
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
        rotulo.setProperty("role", "muted")
        self._lbl_subtotal = QLabel("R$ 0,00")
        self._lbl_subtotal.setProperty("role", "muted")
        linha.addWidget(rotulo)
        linha.addStretch(1)
        linha.addWidget(self._lbl_subtotal)
        col.addLayout(linha)

        linha_desc = QHBoxLayout()
        rotulo_desc = QLabel("Desconto")
        rotulo_desc.setProperty("role", "muted")
        self._lbl_desconto_totais = QLabel("R$ 0,00")
        self._lbl_desconto_totais.setProperty("role", "muted")
        linha_desc.addWidget(rotulo_desc)
        linha_desc.addStretch(1)
        linha_desc.addWidget(self._lbl_desconto_totais)
        col.addLayout(linha_desc)

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
        caixa = QWidget()
        caixa.setObjectName("caixaForma")
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)
        linha.addStretch(1)
        cancelar, self._btn_cancelar = botao_com_atalho("Cancelar", "Esc")
        finalizar, self._btn_salvar = botao_com_atalho(
            "Finalizar venda", "F9", "primary"
        )
        self._btn_salvar.setToolTip("Finalizar venda (F9)")
        self._btn_cancelar.clicked.connect(self._limpar_form)
        self._btn_salvar.clicked.connect(self._salvar)
        linha.addWidget(cancelar)
        linha.addWidget(finalizar)
        return caixa

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
        col.addWidget(barra)

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

        self._vazio = QLabel("Nenhuma venda encontrada. Clique em Nova venda (F6).")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setProperty("role", "muted")
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
        self._cliente.widget.currentIndexChanged.connect(self._cliente_mudou)
        self._forma.widget.currentIndexChanged.connect(self._forma_mudou)
        self._desconto.edicao.textChanged.connect(self._recalcular_totais)
        self._recebido.edicao.textChanged.connect(self._atualizar_troco)
        self._itens_editor.alterado.connect(self._recalcular_totais)

    def _forma_mudou(self) -> None:
        forma = self._forma.valor()
        parcelavel = forma in _FORMAS_PARCELAVEIS
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
        self._lbl_desconto_totais.setText(formatar_moeda(str(desconto)))
        self._lbl_total.setText(formatar_moeda(str(total)))
        n = len(self._itens_editor.valor())
        self._lbl_resumo_itens.setText(f"{n} {'item' if n == 1 else 'itens'}")
        self._atualizar_troco()
        self._atualizar_estado_finalizar()

    def _atualizar_troco(self) -> None:
        if not hasattr(self, "_lbl_troco"):
            return
        recebido = _dec(self._recebido.valor())
        troco = recebido - self._total_venda
        if recebido > 0 and troco < 0:
            # Dinheiro entregue não cobre o total (revisão nº 7): aviso claro.
            self._lbl_troco_rotulo.setText("FALTA")
            self._lbl_troco.setText(formatar_moeda(str(-troco)))
            self._lbl_troco.setProperty("role", "atencao")
        else:
            self._lbl_troco_rotulo.setText("TROCO")
            self._lbl_troco.setText(formatar_moeda(str(troco if troco > 0 else 0)))
            self._lbl_troco.setProperty("role", "success")
        aplicar_estilo(self._lbl_troco)

    def _atualizar_estado_finalizar(self) -> None:
        """Finalizar desabilitado sem itens (revisão nº 4) e no modo leitura."""
        if not hasattr(self, "_btn_salvar"):
            return
        n = len(self._itens_editor.valor())
        if self._modo_leitura:
            self._btn_salvar.setEnabled(False)
            self._btn_salvar.setToolTip("Modo leitura: venda bloqueada pela licença")
        elif n == 0:
            self._btn_salvar.setEnabled(False)
            self._btn_salvar.setToolTip("Adicione ao menos 1 item")
        else:
            self._btn_salvar.setEnabled(True)
            self._btn_salvar.setToolTip("Finalizar venda (F9)")

    def _limpar_form(self) -> None:
        self._itens_editor.limpar()
        self._cliente.definir(None)
        self._vendedor.definir(None)
        self._forma.definir(_FORMA_DINHEIRO)
        self._parcelas.definir("1")
        self._recebido.definir(None)
        self._desconto.definir(None)
        self._pagamento_confirmado.definir(False)
        self._nfce.definir(False)
        self._forma_mudou()
        self._cliente_mudou()

    # ------------------------------------------------------------- abas

    def _ir_para_venda(self) -> None:
        self._vistas.setCurrentIndex(0)
        self._botao_venda.setChecked(True)
        self._botao_historico.setChecked(False)
        self._verificar_caixa()
        if not self._modo_leitura:
            self._itens_editor.focar_busca()

    def _ir_para_historico(self) -> None:
        self._vistas.setCurrentIndex(1)
        self._botao_venda.setChecked(False)
        self._botao_historico.setChecked(True)
        self._busca.focar()

    # ------------------------------------------------------------ busca

    def _aplicar_filtro(self, valor: str) -> None:
        self._filtro = valor
        for v, botao in self._btn_filtros.items():
            botao.setChecked(v == valor)
        self.recarregar(self._busca.texto())

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        return self._api.listar_vendas(
            q=q, status_venda=self._filtro or None, limit=LOTE, offset=offset
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
        self._pilha_lista.setCurrentWidget(
            self._tabela if self._total else self._vazio
        )
        self._btn_exportar.setEnabled(self._total > 0)

    def _erro_carga(self, msg: str) -> None:
        self._tabela.limpar()
        self._vazio.setText(f"Não foi possível carregar as vendas: {msg}")
        self._pilha_lista.setCurrentWidget(self._vazio)
        self._btn_exportar.setEnabled(False)
        QMessageBox.warning(self, "Local API Service", msg)

    def _montar_acoes_linhas(self) -> None:
        coluna = self.CHAVES.index("acoes")
        for linha, dado in enumerate(self._linhas):
            if dado.get("status") == "ok" and not self._modo_leitura:
                botao = QPushButton("Cancelar")
                botao.setObjectName("acaoLinha")
                botao.setProperty("role", "danger")
                botao.clicked.connect(
                    lambda _=False, alvo=dado: self._cancelar_venda(alvo)
                )
                self._tabela.setCellWidget(linha, coluna, botao)
            else:
                vazio = QLabel("—")
                vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vazio.setProperty("role", "muted")
                self._tabela.setCellWidget(linha, coluna, vazio)
            for c in range(len(self.CHAVES)):
                item = self._tabela.item(linha, c)
                if item is not None:
                    item.setToolTip(item.text())

    def _cancelar_venda(self, dado: dict) -> None:
        resposta = QMessageBox.question(
            self,
            "Cancelar venda",
            f"Cancelar a venda Nº {dado.get('numero')}?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        tarefas.rodar(
            lambda: self._api.excluir("vendas", dado["id"]),
            on_ok=lambda _out: self.recarregar(self._busca.texto()),
            on_erro=self._erro_carga,
        )

    # ------------------------------------------------------------ salvar

    def _validar(self):
        if not self._forma.valor():
            return ("Informe a forma de pagamento.", self._forma)
        if self._forma.valor() in _FORMAS_PARCELAVEIS:
            parcelas = (self._parcelas.valor() or "").strip()
            if not parcelas.isdigit() or int(parcelas) < 1:
                return ("Parcelas deve ser um número maior que zero.", self._parcelas)
        if not self._itens_editor.valor():
            return ("Adicione ao menos um item à venda.", self._itens_editor)
        exigencia = self._exigencia_pendente()
        if exigencia:
            return (
                f"O cliente exige {exigencia}. Marque 'Pagamento já recebido' "
                "para finalizar a venda.",
                self._pagamento_confirmado,
            )
        return None

    def _payload(self) -> dict:
        forma = self._forma.valor()
        if forma in _FORMAS_PARCELAVEIS:
            parcelas = int((self._parcelas.valor() or "1").strip() or "1")
        else:
            parcelas = 1
        return {
            "cliente_id": self._cliente.valor(),
            "vendedor_id": self._vendedor.valor(),
            "desconto": str(_dec(self._desconto.valor())),
            "forma_pagamento": forma,
            "parcelas": parcelas,
            "pagamento_confirmado": self._pagamento_confirmado.valor(),
            "itens": self._itens_editor.valor(),
        }

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
            return formatar_data_iso(dado.get("data_venda"))
        if chave == "cliente_nome":
            return dado.get("cliente_nome") or "Consumidor final"
        if chave == "forma_pagamento":
            valor = str(dado.get("forma_pagamento") or "")
            return _ROTULO_PAGAMENTO.get(valor, valor.upper())
        if chave == "valor_total":
            return formatar_moeda(dado.get("valor_total"))
        if chave == "status":
            valor = str(dado.get("status") or "")
            return _ROTULO_STATUS.get(valor, valor.upper())
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
        # assim F6/F9 não disparam enquanto outra tela está ativa (ex.: F9 numa
        # venda em andamento finalizaria o registro às escondidas).
        atalho_nova = QShortcut(QKeySequence("F6"), self)
        atalho_nova.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho_nova.activated.connect(self._ir_para_venda)

        atalho_finalizar = QShortcut(QKeySequence("F9"), self)
        atalho_finalizar.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atalho_finalizar.activated.connect(self._salvar)

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
        self._banner_caixa = QWidget()
        self._banner_caixa.setObjectName("bannerAviso")
        linha = QHBoxLayout(self._banner_caixa)
        linha.setContentsMargins(12, 8, 12, 8)
        linha.setSpacing(10)
        rotulo = QLabel("Caixa fechado — abra o caixa antes de registrar vendas.")
        rotulo.setProperty("role", "atencao")
        linha.addWidget(rotulo, 1)
        botao = QPushButton("Abrir caixa")
        botao.setObjectName("acaoLinha")
        botao.clicked.connect(self._abrir_tela_caixa)
        linha.addWidget(botao)
        self._banner_caixa.setVisible(False)
        return self._banner_caixa

    def _abrir_tela_caixa(self) -> None:
        alvo = "caixa" if pode_abrir(self._nivel, "caixa") else "financeiro"
        self.navegar.emit(alvo)

    def _verificar_caixa(self) -> None:
        """Consulta o caixa do vendedor logado; `None` = fechado → banner."""
        if self._modo_leitura or not self._api.autenticado:
            return

        def ok(caixa) -> None:
            self._banner_caixa.setVisible(caixa is None)

        def erro(_msg) -> None:
            # Sem resposta do daemon: o banner fica como está — quem bloqueia
            # é o servidor (409 com a mensagem clara no Finalizar).
            pass

        tarefas.rodar(self._api.caixa_atual, ok, erro)

    def showEvent(self, evento) -> None:  # noqa: N802 (API do Qt)
        super().showEvent(evento)
        self._verificar_caixa()
        if self._vistas.currentIndex() == 0 and not self._modo_leitura:
            self._itens_editor.focar_busca()
