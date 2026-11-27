"""Grade de itens de O.S./Orçamento/Venda — o coração da tela de orçamento.

Cada linha guarda o contrato do daemon (`OsItemIn`) e, para itens de
fornecedor, os dados internos de precificação (`vf`, `custo`, `estado_cotacao`):

    CP = VF × 2,30   (arredondado em 2 casas, ROUND_HALF_UP)
    VO = CP × 1,06   (sobre o CP já arredondado — regra Q-01 do backend)

O VF pode ser digitado diretamente na coluna "VF (R$)" ou no editor abaixo da
grade. O custo e o preço unitário são calculados na hora: o operador não faz
conta de cabeça e a linha fica amarela enquanto não há cotação aprovada.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
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
from printgest.ui.formulario import formatar_moeda, para_decimal
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import estado_atencao, estado_muted, estado_primario

_CHAVES = [
    "seq", "descricao", "dimensoes", "quantidade", "vf", "custo",
    "valor_unitario", "desconto", "valor_total", "situacao", "acao",
]
_ROTULOS = [
    "#", "Especificação", "Dimensões", "Qtd.", "VF (R$)", "Custo (CP)",
    "Preço Unit.", "Desc.", "Total", "Situação", "Ação",
]
_PESOS = [2, 15, 8, 5, 8, 8, 9, 7, 9, 12, 10]

# Colunas editáveis diretamente na grade.
_COL_VF, _COL_UNIT, _COL_DESCONTO = 4, 6, 7

_CENTAVOS = Decimal("0.01")
_FATOR_CP = Decimal("2.30")   # 130% de acréscimo sobre o fornecedor
_FATOR_VO = Decimal("1.06")   # 6% de markup sobre o CP
_COR_PENDENTE = QColor("#FFF4E8")
_COR_TEXTO_ATENCAO = QColor("#B25000")

_AVULSO = None  # data do combo de produtos: "descrever serviço avulso"


def _dec(valor):
    """Decimal tolerante ao formato brasileiro ('1.234,56'); vazio/inválido → 0."""
    dec = para_decimal(valor)
    return Decimal("0") if dec is None else dec


def _moeda_item(valor) -> str:
    """Campos opcionais zerados mostram '—' em vez de mais um 'R$ 0,00'."""
    return "—" if _dec(valor) == 0 else formatar_moeda(str(_dec(valor)))


def calcular_preco(vf) -> tuple[Decimal, Decimal]:
    """(CP, VO) a partir do VF, seguindo a sequência normativa do backend."""
    custo = (_dec(vf) * _FATOR_CP).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    final = (custo * _FATOR_VO).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    return custo, final


class GradeItens(QWidget):
    """Cumpre o contrato de `CampoForm` (widget, valor, definir, habilitar) + `largo`."""

    largo = True
    alterado = Signal()
    selecao_alterada = Signal()
    cotacao_solicitada = Signal(object)  # item de fornecedor → abrir cotações

    def __init__(self, rotulo: str = "Itens", api: Api | None = None) -> None:
        super().__init__()
        self._api = api
        self._itens: list[dict] = []
        self._produtos: dict[int, dict] = {}
        self._editando: int | None = None
        self._preenchendo = False

        self._rotulo = QLabel(rotulo.upper()) if rotulo else None
        if self._rotulo is not None:
            self._rotulo.setObjectName("labelForm")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._tabela = TabelaDensa(_CHAVES, _ROTULOS, pesos=_PESOS)
        self._tabela.setMinimumHeight(200)
        self._tabela.estado_vazio("Nenhum item. Use “+ Adicionar Novo Item” abaixo.")
        self._tabela.itemSelectionChanged.connect(self._selecao_mudou)
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

    # -------------------------------------------------------------- editor

    def _barra_editor(self) -> QWidget:
        """Editor em duas etapas: (1) o que é, (2) quanto custa — botões à parte."""
        caixa = QWidget()
        caixa.setObjectName("card")
        grade = QGridLayout(caixa)
        grade.setContentsMargins(10, 8, 10, 8)
        grade.setHorizontalSpacing(8)
        grade.setVerticalSpacing(4)
        for coluna, stretch in enumerate((2, 2, 2, 1, 1, 1)):
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
            "Item terceirizado: o VF alimenta CP e Preço Unitário automaticamente."
        )
        self._check_fornecedor.toggled.connect(self._origem_mudou)

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
        self._vf = QLineEdit()
        self._vf.setPlaceholderText("0,00")
        self._vf.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._vf.setToolTip("2) VF — valor do fornecedor (gera CP e preço automaticamente)")
        self._vf.setEnabled(False)
        self._unit = QLineEdit()
        self._unit.setPlaceholderText("0,00")
        self._unit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._unit.setToolTip("2) Valor unitário (itens próprios)")
        self._desconto = QLineEdit()
        self._desconto.setPlaceholderText("0,00")
        self._desconto.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._desconto.setToolTip("2) Desconto em reais (opcional)")

        grade.addWidget(rotulo("Qtd."), 2, 0)
        grade.addWidget(rotulo("Dimensões"), 2, 1)
        grade.addWidget(rotulo("VF (R$) — fornecedor"), 2, 2)
        grade.addWidget(rotulo("Preço Unit. (R$)"), 2, 3)
        grade.addWidget(rotulo("Desc. (R$)"), 2, 4)
        grade.addWidget(self._qtd, 3, 0)
        grade.addWidget(self._dimensoes, 3, 1)
        grade.addWidget(self._vf, 3, 2)
        grade.addWidget(self._unit, 3, 3)
        grade.addWidget(self._desconto, 3, 4)

        self._btn_adicionar = QPushButton("+ Adicionar Novo Item")
        self._btn_adicionar.setToolTip("Adicionar item (Enter nos campos)")
        estado_primario(self._btn_adicionar)
        self._btn_adicionar.clicked.connect(self._adicionar)
        for w in (
            self._descricao, self._qtd, self._dimensoes,
            self._vf, self._unit, self._desconto,
        ):
            w.returnPressed.connect(self._adicionar)
        self._btn_adicionar.setMinimumWidth(150)

        self._btn_cancelar_edicao = QPushButton("Cancelar edição")
        self._btn_cancelar_edicao.setVisible(False)
        self._btn_cancelar_edicao.clicked.connect(self._sair_edicao)

        remover = QPushButton("Remover Selecionada")
        remover.clicked.connect(self._remover)
        remover.setMinimumWidth(120)

        botoes = QHBoxLayout()
        botoes.setSpacing(8)
        botoes.addWidget(remover)
        botoes.addWidget(self._btn_cancelar_edicao)
        botoes.addStretch(1)
        botoes.addWidget(self._btn_adicionar)
        grade.addLayout(botoes, 4, 0, 1, 6)
        return caixa

    # ------------------------------------------------------------ produtos

    def carregar(self, api: Api) -> None:
        self._api = api
        catalogos.carregar(
            "produtos",
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

    def _origem_mudou(self, marcado: bool) -> None:
        self._vf.setEnabled(marcado)
        self._unit.setEnabled(not marcado)

    # --------------------------------------------------------------- itens

    @staticmethod
    def _pendente(item: dict) -> bool:
        return (
            (item.get("tipo") or "proprio") == "fornecedor"
            and item.get("estado_cotacao") != "cotado"
            and _dec(item.get("vf")) == 0
        )

    def itens_pendentes(self) -> list[dict]:
        """Itens que impedem a conversão em O.S."""
        return [item for item in self._itens if self._pendente(item)]

    def aplicar_cotacao(self, item_id, snapshot: dict) -> None:
        """Reflete no item o snapshot VF/CP/VO aprovado no modal de cotações."""
        for item in self._itens:
            if item.get("id") == item_id and snapshot:
                item["vf"] = str(snapshot.get("vf") or "0")
                item["custo"] = str(snapshot.get("cp") or "0")
                item["valor_unitario"] = str(snapshot.get("vo") or "0")
                item["estado_cotacao"] = "cotado"
        self._atualizar()

    def _adicionar(self) -> None:
        pid = self._combo_produto.currentData()
        descricao = self._descricao.text().strip()
        if pid is None and not descricao:
            QMessageBox.warning(
                self, "Item", "Escolha um produto ou informe a descrição avulsa."
            )
            return
        fornecedor = self._check_fornecedor.isChecked()
        qtd = _dec(self._qtd.text()) or Decimal("1")
        novo = {
            "produto_id": pid,
            "descricao_avulsa": None if pid is not None else descricao,
            "quantidade": str(qtd),
            "dimensoes": self._dimensoes.text().strip() or None,
            "desconto": str(_dec(self._desconto.text())),
            "tipo": "fornecedor" if fornecedor else "proprio",
            "vf": None,
            "custo": None,
        }
        if fornecedor:
            vf = _dec(self._vf.text())
            if vf > 0:
                cp, vo = calcular_preco(vf)
                novo.update({
                    "vf": str(vf), "custo": str(cp),
                    "valor_unitario": str(vo), "estado_cotacao": "cotado",
                })
            else:
                novo.update({"valor_unitario": "0", "estado_cotacao": "aguardando"})
        else:
            novo["valor_unitario"] = str(_dec(self._unit.text()))

        if self._editando is not None and 0 <= self._editando < len(self._itens):
            self._itens[self._editando] = novo
        else:
            self._itens.append(novo)
        self._limpar_editor()
        self._atualizar()
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
        for campo in (self._descricao, self._dimensoes, self._vf, self._unit, self._desconto):
            campo.clear()
        self._qtd.setText("1")
        self._check_fornecedor.setChecked(False)
        self._btn_adicionar.setText("+ Adicionar Novo Item")
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
        self._vf.setText(str(item.get("vf") or ""))
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
            if GradeItens._pendente(item):
                return "Item de fornecedor — aguardando cotação (VF)."
            return "Item de fornecedor — preço calculado a partir do VF."
        return "Item próprio — produção interna."

    # ------------------------------------------------------------- tabela

    def _celula_alterada(self, celula) -> None:
        """Edição direta: VF gera CP/VO; preço e desconto são do item próprio."""
        if self._preenchendo:
            return
        linha = celula.row()
        if not 0 <= linha < len(self._itens):
            return
        item = self._itens[linha]
        coluna = celula.column()
        if coluna == _COL_VF and (item.get("tipo") or "proprio") == "fornecedor":
            vf = _dec(celula.text())
            if vf > 0:
                cp, vo = calcular_preco(vf)
                item["vf"] = str(vf)
                item["custo"] = str(cp)
                item["valor_unitario"] = str(vo)
                item["estado_cotacao"] = "cotado"
            else:
                item["vf"] = None
                item["custo"] = None
                item["valor_unitario"] = "0"
                item["estado_cotacao"] = "aguardando"
        elif coluna == _COL_UNIT and (item.get("tipo") or "proprio") != "fornecedor":
            item["valor_unitario"] = str(_dec(celula.text()))
        elif coluna == _COL_DESCONTO:
            item["desconto"] = str(_dec(celula.text()))
        else:
            return
        self._atualizar()

    def _linhas_display(self) -> list[dict]:
        linhas = []
        for seq, item in enumerate(self._itens, start=1):
            produto = self._produtos.get(item.get("produto_id"))
            descricao = (
                (produto or {}).get("nome")
                or item.get("descricao_avulsa")
                or "—"
            )
            tipo = item.get("tipo") or "proprio"
            pendente = self._pendente(item)
            if tipo == "fornecedor":
                tipo_texto = (
                    "⚠ Fornecedor • Aguardando"
                    if pendente else "✓ Fornecedor • Cotado"
                )
                situacao = "⚠ Cotação pendente" if pendente else "✓ Cotado"
            else:
                tipo_texto = "Próprio"
                situacao = "—"
            total = (
                _dec(item.get("valor_unitario")) * _dec(item.get("quantidade"))
                - _dec(item.get("desconto"))
            )
            linhas.append({
                "seq": f"{seq:02d}",
                "descricao": descricao,
                "dimensoes": item.get("dimensoes") or "",
                "quantidade": str(item.get("quantidade") or ""),
                "vf": _moeda_item(item.get("vf")),
                "custo": _moeda_item(item.get("custo")),
                "valor_unitario": (
                    "Aguard. Cotação" if pendente and tipo == "fornecedor"
                    else _moeda_item(item.get("valor_unitario"))
                ),
                "desconto": _moeda_item(item.get("desconto")),
                "valor_total": (
                    "Aguardando cotação" if pendente and tipo == "fornecedor"
                    else formatar_moeda(str(total))
                ),
                "situacao": situacao,
                "acao": "",  # preenchido por _atualizar() com botão na linha
                "tipo": tipo_texto,  # compatibilidade com testes/relatórios
            })
        return linhas

    def _atualizar(self) -> None:
        self._preenchendo = True
        self._tabela.preencher(self._linhas_display())
        for linha, item in enumerate(self._itens):
            pendente = self._pendente(item)
            fornecedor = (item.get("tipo") or "proprio") == "fornecedor"
            for coluna in range(self._tabela.columnCount()):
                celula = self._tabela.item(linha, coluna)
                if celula is None:
                    continue
                flags = celula.flags()
                editavel = (
                    (coluna == _COL_VF and fornecedor)
                    or (coluna == _COL_UNIT and not fornecedor)
                    or coluna == _COL_DESCONTO
                )
                if editavel:
                    flags |= Qt.ItemFlag.ItemIsEditable
                    celula.setToolTip("Duplo clique para editar")
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                celula.setFlags(flags)
                if pendente:
                    celula.setBackground(QBrush(_COR_PENDENTE))
                    if coluna in (9, 10):
                        celula.setForeground(QBrush(_COR_TEXTO_ATENCAO))
            if pendente:
                botao = QPushButton("Lançar Cotação")
                botao.setObjectName("acaoLinha")
                botao.setToolTip("Abrir o comparativo de fornecedores deste item")
                botao.clicked.connect(
                    lambda _=False, i=dict(item): self.cotacao_solicitada.emit(i)
                )
                self._tabela.setCellWidget(linha, 10, botao)
        self._preenchendo = False

        total = sum(
            (_dec(i["valor_unitario"]) * _dec(i["quantidade"]) - _dec(i["desconto"]))
            for i in self._itens
        )
        quantidade = len(self._itens)
        palavra = "item" if quantidade == 1 else "itens"
        self._resumo.setText(
            f"Itens ({quantidade}): {formatar_moeda(str(total))}"
        )
        pendentes = len(self.itens_pendentes())
        if pendentes:
            verbo = "item aguarda" if pendentes == 1 else "itens aguardam"
            self._aviso_pendente.setText(
                f"⚠ {pendentes} {verbo} cotação — lance o VF na linha destacada "
                "ou use “Lançar Cotação”."
            )
            self._aviso_pendente.setVisible(True)
        else:
            self._aviso_pendente.clear()
            self._aviso_pendente.setVisible(False)
        self.alterado.emit()

    # ---------------------------------------------------------- formulário

    @property
    def item_selecionado(self) -> dict | None:
        """Item da linha selecionada (dados internos, não display)."""
        linha = self._tabela.currentRow()
        if 0 <= linha < len(self._itens):
            return dict(self._itens[linha])
        return None

    @property
    def rotulo_widget(self) -> QWidget | None:
        return self._rotulo

    @property
    def widget(self) -> QWidget:
        return self

    def valor(self) -> list[dict]:
        return [dict(i) for i in self._itens]

    def definir(self, lista) -> None:
        self._itens = []
        for bruto in (lista or []):
            item = dict(bruto)
            item.setdefault("vf", None)
            item.setdefault("custo", None)
            self._itens.append(item)
        self._limpar_editor()
        self._atualizar()

    def habilitar(self, ligado: bool) -> None:
        for widget in (
            self._combo_produto, self._descricao, self._qtd, self._dimensoes,
            self._vf, self._unit, self._desconto, self._check_fornecedor,
        ):
            widget.setEnabled(ligado)
        self._origem_mudou(self._check_fornecedor.isChecked() and ligado)
        for botao in self.findChildren(QPushButton):
            botao.setEnabled(ligado)
