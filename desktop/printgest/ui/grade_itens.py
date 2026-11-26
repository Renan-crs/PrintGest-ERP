"""Grade de itens de O.S./Orçamento/Venda — linhas com produto ou avulso.

Cada linha guarda exatamente o contrato do daemon (`OsItemIn`/`VendaItemIn`):
`{produto_id, descricao_avulsa, quantidade, dimensoes, valor_unitario, desconto}`.
O widget também carrega o catálogo de produtos (para o combo e o mapa de nomes).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.api import Api
from printgest.ui.widgets import estado_atencao, estado_muted, estado_primario
from printgest.ui.formulario import CampoValor, formatar_moeda, para_decimal
from printgest.ui.tabela import TabelaDensa

_CHAVES = ["seq", "descricao", "tipo", "quantidade", "dimensoes", "valor_unitario", "desconto", "valor_total"]
_ROTULOS = ["#", "Especificação", "Tipo", "Qtd.", "Dimensões", "Unit.", "Desc.", "Total"]
# "Fornecedor • Aguardando" precisa de espaço próprio para não elidir o estado.
_PESOS = [2, 16, 12, 6, 10, 9, 8, 10]

_AVULSO = None  # data do combo de produtos: "descrever serviço avulso"


def _dec(valor):
    """Decimal tolerante ao formato brasileiro ('1.234,56'); vazio/inválido → 0."""
    dec = para_decimal(valor)
    return Decimal("0") if dec is None else dec


def _moeda_item(valor) -> str:
    """Campos opcionais zerados mostram '—' em vez de mais um 'R$ 0,00'."""
    return "—" if _dec(valor) == 0 else formatar_moeda(str(_dec(valor)))


class GradeItens(QWidget):
    """Cumpre o contrato de `CampoForm` (widget, valor, definir, habilitar) + `largo`."""

    largo = True
    alterado = Signal()
    selecao_alterada = Signal()

    def __init__(self, rotulo: str = "Itens", api: Api | None = None) -> None:
        super().__init__()
        self._api = api
        self._itens: list[dict] = []
        self._produtos: dict[int, dict] = {}
        self._editando: int | None = None
        self._preenchendo = False

        # Sem rótulo próprio: o cabeçalho da seção do formulário já nomeia a grade.
        self._rotulo = QLabel(rotulo.upper()) if rotulo else None
        if self._rotulo is not None:
            self._rotulo.setObjectName("labelForm")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._tabela = TabelaDensa(_CHAVES, _ROTULOS, pesos=_PESOS)
        self._tabela.setMinimumHeight(160)
        self._tabela.estado_vazio("Nenhum item. Adicione um no formulário abaixo.")
        self._tabela.itemSelectionChanged.connect(self._selecao_mudou)
        # Edição direta do valor unitário (duplo clique), sem exigir cotação.
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._tabela.itemChanged.connect(self._celula_alterada)
        layout.addWidget(self._tabela)

        layout.addWidget(self._barra_editor())

        self._resumo = QLabel("0 itens • Subtotal: R$ 0,00")
        estado_muted(self._resumo)
        layout.addWidget(self._resumo)

        self._aviso_pendente = QLabel("")
        estado_atencao(self._aviso_pendente)
        self._aviso_pendente.setWordWrap(True)
        self._aviso_pendente.setVisible(False)
        layout.addWidget(self._aviso_pendente)

        if api is not None:
            self.carregar(api)

    def _barra_editor(self) -> QWidget:
        """Editor em duas etapas: (1) o que é, (2) quanto custa — botões à parte."""
        caixa = QWidget()
        caixa.setObjectName("card")
        grade = QGridLayout(caixa)
        grade.setContentsMargins(10, 8, 10, 8)
        grade.setHorizontalSpacing(8)
        grade.setVerticalSpacing(4)
        for coluna, stretch in enumerate((2, 2, 2, 1, 1)):
            grade.setColumnStretch(coluna, stretch)

        def rotulo(texto: str) -> QLabel:
            lbl = QLabel(texto)
            lbl.setObjectName("labelForm")
            return lbl

        self._combo_produto = QComboBox()
        self._combo_produto.setMinimumWidth(180)
        self._combo_produto.currentIndexChanged.connect(self._produto_selecionado)
        self._combo_produto.setToolTip("1) Selecione um produto cadastrado")

        self._descricao = QLineEdit()
        self._descricao.setPlaceholderText("Ou descreva o serviço avulso")
        self._descricao.setMinimumWidth(140)
        self._descricao.setToolTip("Usado quando nenhum produto é selecionado")

        self._check_fornecedor = QCheckBox("Fornecedor")
        self._check_fornecedor.setToolTip(
            "Item terceirizado: entra como “Aguardando cotação” até alguém "
            "com permissão lançar e selecionar a cotação do fornecedor."
        )
        grade.addWidget(rotulo("1) Produto / serviço"), 0, 0)
        grade.addWidget(rotulo("Descrição avulsa"), 0, 1)
        grade.addWidget(rotulo("Origem"), 0, 2)
        grade.addWidget(self._combo_produto, 1, 0)
        grade.addWidget(self._descricao, 1, 1)
        grade.addWidget(self._check_fornecedor, 1, 2)

        self._qtd = QLineEdit("1")
        self._qtd.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._qtd.setMaximumWidth(80)
        self._qtd.setToolTip("2) Quantidade")
        self._dimensoes = QLineEdit()
        self._dimensoes.setPlaceholderText("Ex.: 5x10 cm")
        self._dimensoes.setToolTip("2) Dimensões do serviço (opcional)")
        self._unit = QLineEdit()
        self._unit.setPlaceholderText("0,00")
        self._unit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._unit.setToolTip("2) Valor unitário em reais")
        self._desconto = QLineEdit()
        self._desconto.setPlaceholderText("0,00")
        self._desconto.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._desconto.setToolTip("2) Desconto em reais (opcional)")

        grade.addWidget(rotulo("Qtd."), 2, 0)
        grade.addWidget(rotulo("Dimensões"), 2, 1)
        grade.addWidget(rotulo("Valor unitário (R$)"), 2, 2)
        grade.addWidget(rotulo("Desconto (R$)"), 2, 3)
        grade.addWidget(self._qtd, 3, 0)
        grade.addWidget(self._dimensoes, 3, 1)
        grade.addWidget(self._unit, 3, 2)
        grade.addWidget(self._desconto, 3, 3)

        self._btn_adicionar = QPushButton("Adicionar")
        self._btn_adicionar.setToolTip("Adicionar item (Enter nos campos)")
        estado_primario(self._btn_adicionar)
        self._btn_adicionar.clicked.connect(self._adicionar)
        # Enter nos campos de edição adiciona o item (refinamento de fluxo)
        for w in (self._descricao, self._qtd, self._dimensoes, self._unit, self._desconto):
            w.returnPressed.connect(self._adicionar)
        self._btn_adicionar.setMinimumWidth(100)

        self._btn_cancelar_edicao = QPushButton("Cancelar edição")
        self._btn_cancelar_edicao.setVisible(False)
        self._btn_cancelar_edicao.clicked.connect(self._sair_edicao)

        remover = QPushButton("Remover Selecionada")
        remover.clicked.connect(self._remover)
        remover.setMinimumWidth(120)

        botoes = QHBoxLayout()
        botoes.setSpacing(8)
        botoes.addStretch(1)
        botoes.addWidget(self._btn_cancelar_edicao)
        botoes.addWidget(remover)
        botoes.addWidget(self._btn_adicionar)
        grade.addLayout(botoes, 4, 0, 1, 5)
        return caixa

    # ------------------------------------------------------------ produtos

    def carregar(self, api: Api) -> None:
        self._api = api
        catalogos.carregar(
            "produtos",
            # Mesmo catálogo completo do PDV (sem o teto de 200 da fábrica).
            lambda: api.listar("pdv/produtos", limit=1000),
            on_ok=self._produtos_recebidos,
        )

    def _produtos_recebidos(self, saida: dict) -> None:
        self._produtos = {
            r["id"]: {"nome": r.get("nome", ""), "preco_venda": r.get("preco_venda")}
            for r in saida.get("data", [])
        }
        self._combo_produto.blockSignals(True)
        self._combo_produto.clear()
        self._combo_produto.addItem("— Descrever serviço avulso —", _AVULSO)
        for r in saida.get("data", []):
            rotulo = f"{r.get('codigo', '')} • {r.get('nome', '')}".strip(" •")
            self._combo_produto.addItem(rotulo, r["id"])
        self._combo_produto.setCurrentIndex(0)
        self._combo_produto.blockSignals(False)

    def _produto_selecionado(self) -> None:
        pid = self._combo_produto.currentData()
        avulso = pid is None
        self._descricao.setEnabled(avulso)
        if not avulso and not self._unit.text().strip():
            self._unit.setText(str(self._produtos.get(pid, {}).get("preco_venda") or ""))

    # ------------------------------------------------------------ itens

    def _adicionar(self) -> None:
        pid = self._combo_produto.currentData()
        descricao = self._descricao.text().strip()
        if pid is None and not descricao:
            QMessageBox.warning(
                self, "Item", "Escolha um produto ou informe a descrição avulsa."
            )
            return
        qtd = _dec(self._qtd.text())
        if qtd <= 0:
            qtd = Decimal("1")
        novo = {
            "produto_id": pid,
            "descricao_avulsa": None if pid is not None else descricao,
            "quantidade": str(qtd),
            "dimensoes": self._dimensoes.text().strip() or None,
            "valor_unitario": str(_dec(self._unit.text())),
            "desconto": str(_dec(self._desconto.text())),
            "tipo": "fornecedor" if self._check_fornecedor.isChecked() else "proprio",
        }
        if self._editando is not None and 0 <= self._editando < len(self._itens):
            self._itens[self._editando] = novo
        else:
            self._itens.append(novo)
        self._limpar_editor()
        self._atualizar()
        # fluxo contínuo: prepara próximo item
        if self._combo_produto.currentData() is None:
            self._descricao.setFocus()
        else:
            self._combo_produto.setFocus()

    def _remover(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._itens):
            return
        del self._itens[linha]
        self._limpar_editor()
        self._atualizar()

    # --------------------------------------------------------- edição de linha

    def _limpar_editor(self) -> None:
        self._editando = None
        self._descricao.clear()
        self._dimensoes.clear()
        self._unit.clear()
        self._desconto.clear()
        self._qtd.setText("1")
        self._check_fornecedor.setChecked(False)
        self._btn_adicionar.setText("Adicionar")
        self._btn_adicionar.setToolTip("Adicionar item (Enter nos campos)")
        self._btn_cancelar_edicao.setVisible(False)

    def _sair_edicao(self) -> None:
        self._limpar_editor()

    def _selecao_mudou(self) -> None:
        linha = self._tabela.currentRow()
        if 0 <= linha < len(self._itens):
            self._editando = linha
            self._carregar_para_edicao(self._itens[linha])
        else:
            self._limpar_editor()
        self.selecao_alterada.emit()

    def _carregar_para_edicao(self, item: dict) -> None:
        pid = item.get("produto_id")
        indice = self._combo_produto.findData(pid)
        self._combo_produto.setCurrentIndex(indice if indice >= 0 else 0)
        self._descricao.setText(str(item.get("descricao_avulsa") or ""))
        self._descricao.setEnabled(pid is None)
        self._qtd.setText(str(item.get("quantidade") or "1"))
        self._dimensoes.setText(str(item.get("dimensoes") or ""))
        self._unit.setText(str(item.get("valor_unitario") or ""))
        self._desconto.setText(str(item.get("desconto") or ""))
        self._check_fornecedor.setChecked(
            (item.get("tipo") or "proprio") == "fornecedor"
        )
        self._btn_adicionar.setText("Salvar item")
        self._btn_adicionar.setToolTip("Salvar alterações no item selecionado")
        self._btn_cancelar_edicao.setVisible(True)

    @staticmethod
    def _dica_tipo(item: dict) -> str:
        if (item.get("tipo") or "proprio") == "fornecedor":
            if item.get("estado_cotacao") == "cotado":
                return "Item de fornecedor — cotação aprovada."
            return (
                "Item de fornecedor — aguardando cotação. "
                "Abra “Cotações” para lançar e aprovar."
            )
        return "Item próprio — produção interna."

    def _celula_alterada(self, celula) -> None:
        """Valor unitário editado na grade: reflete no payload sem abrir cotações."""
        if self._preenchendo or celula.column() != 5:
            return
        linha = celula.row()
        if not 0 <= linha < len(self._itens):
            return
        valor = para_decimal(celula.text(), "R$")
        self._itens[linha]["valor_unitario"] = str(valor or Decimal("0"))
        self._atualizar()

    def _atualizar(self) -> None:
        self._preenchendo = True
        self._tabela.preencher(self._linhas_display())
        for linha, item in enumerate(self._itens):
            pendente = (
                (item.get("tipo") or "proprio") == "fornecedor"
                and item.get("estado_cotacao") != "cotado"
            )
            for coluna in range(self._tabela.columnCount()):
                celula = self._tabela.item(linha, coluna)
                if celula is None:
                    continue
                flags = celula.flags()
                if coluna == 5:  # Unit.: único campo editável na grade
                    celula.setToolTip("Duplo clique para editar o valor unitário")
                    flags |= Qt.ItemFlag.ItemIsEditable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                    if coluna == 2:
                        celula.setToolTip(self._dica_tipo(item))
                celula.setFlags(flags)
                if pendente and coluna in (2, 7):
                    celula.setForeground(QColor("#B25000"))
        self._preenchendo = False

        total = sum(
            (_dec(i["valor_unitario"]) * _dec(i["quantidade"]) - _dec(i["desconto"]))
            for i in self._itens
        )
        quantidade = len(self._itens)
        palavra = "item" if quantidade == 1 else "itens"
        self._resumo.setText(
            f"{quantidade} {palavra} • Subtotal: {formatar_moeda(str(total))}"
        )
        pendentes = sum(
            1 for i in self._itens
            if (i.get("tipo") or "proprio") == "fornecedor"
            and i.get("estado_cotacao") != "cotado"
        )
        if pendentes:
            verbo = "item aguarda" if pendentes == 1 else "itens aguardam"
            self._aviso_pendente.setText(
                f"⚠ {pendentes} {verbo} cotação — dê duplo clique no valor "
                "unitário da grade ou abra “Cotações” no rodapé."
            )
            self._aviso_pendente.setVisible(True)
        else:
            self._aviso_pendente.clear()
            self._aviso_pendente.setVisible(False)
        self.alterado.emit()

    def _linhas_display(self) -> list[dict]:
        linhas = []
        for seq, item in enumerate(self._itens, start=1):
            produto = self._produtos.get(item.get("produto_id"))
            descricao = (
                (produto or {}).get("nome")
                or item.get("descricao_avulsa")
                or "—"
            )
            # M1: coluna Tipo com o estado da cotação (§3.2.2)
            tipo = item.get("tipo") or "proprio"
            estado = item.get("estado_cotacao")
            if tipo == "fornecedor":
                tipo_texto = (
                    "⚠ Fornecedor • Aguardando"
                    if estado != "cotado"
                    else "✓ Fornecedor • Cotado"
                )
            else:
                tipo_texto = "Próprio"
            total = (
                _dec(item.get("valor_unitario")) * _dec(item.get("quantidade"))
                - _dec(item.get("desconto"))
            )
            valor_total = (
                "Aguardando cotação"
                if tipo == "fornecedor" and estado != "cotado"
                else formatar_moeda(str(total))
            )
            linhas.append(
                {
                    "seq": f"{seq:02d}",
                    "descricao": descricao,
                    "tipo": tipo_texto,
                    "quantidade": str(item.get("quantidade") or ""),
                    "dimensoes": item.get("dimensoes") or "",
                    "valor_unitario": _moeda_item(item.get("valor_unitario")),
                    "desconto": _moeda_item(item.get("desconto")),
                    "valor_total": valor_total,
                }
            )
        return linhas

    @property
    def item_selecionado(self) -> dict | None:
        """Item da linha selecionada (com dados internos, não display)."""
        linha = self._tabela.currentRow()
        if 0 <= linha < len(self._itens):
            return dict(self._itens[linha])
        return None

    # ---------------------------------------------------------- formulário

    @property
    def rotulo_widget(self) -> QWidget | None:
        return self._rotulo

    @property
    def widget(self) -> QWidget:
        return self

    def valor(self) -> list[dict]:
        return [dict(i) for i in self._itens]

    def definir(self, lista) -> None:
        self._itens = [dict(i) for i in (lista or [])]
        self._limpar_editor()
        self._atualizar()

    def habilitar(self, ligado: bool) -> None:
        for widget in (
            self._combo_produto,
            self._descricao,
            self._qtd,
            self._dimensoes,
            self._unit,
            self._desconto,
            self._check_fornecedor,
        ):
            widget.setEnabled(ligado)
        for botao in self.findChildren(QPushButton):
            botao.setEnabled(ligado)