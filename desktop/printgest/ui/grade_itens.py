"""Grade de itens de O.S./Orçamento/Venda — linhas com produto ou avulso.

Cada linha guarda exatamente o contrato do daemon (`OsItemIn`/`VendaItemIn`):
`{produto_id, descricao_avulsa, quantidade, dimensoes, valor_unitario, desconto}`.
O widget também carrega o catálogo de produtos (para o combo e o mapa de nomes).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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
from printgest.ui.formulario import CampoValor, formatar_moeda, para_decimal
from printgest.ui.tabela import TabelaDensa

_CHAVES = ["seq", "descricao", "quantidade", "dimensoes", "valor_unitario", "desconto", "valor_total"]
_ROTULOS = ["#", "Especificação", "Quant.", "Dimensões", "Unit.", "Desc.", "Total"]

_AVULSO = None  # data do combo de produtos: "descrever serviço avulso"


def _dec(valor):
    """Decimal tolerante ao formato brasileiro ('1.234,56'); vazio/inválido → 0."""
    dec = para_decimal(valor)
    return Decimal("0") if dec is None else dec


class GradeItens(QWidget):
    """Cumpre o contrato de `CampoForm` (widget, valor, definir, habilitar) + `largo`."""

    largo = True
    alterado = Signal()

    def __init__(self, rotulo: str = "Itens", api: Api | None = None) -> None:
        super().__init__()
        self._api = api
        self._itens: list[dict] = []
        self._produtos: dict[int, dict] = {}

        # Sem rótulo próprio: o cabeçalho da seção do formulário já nomeia a grade.
        self._rotulo = QLabel(rotulo.upper()) if rotulo else None
        if self._rotulo is not None:
            self._rotulo.setObjectName("labelForm")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._tabela = TabelaDensa(_CHAVES, _ROTULOS)
        self._tabela.setMinimumHeight(140)
        layout.addWidget(self._tabela)

        layout.addWidget(self._barra_editor())

        self._resumo = QLabel("0 itens • Subtotal: R$ 0,00")
        self._resumo.setProperty("role", "muted")
        layout.addWidget(self._resumo)

        if api is not None:
            self.carregar(api)

    def _barra_editor(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("card")
        layout = QVBoxLayout(caixa)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Linha 1: Produto + Descrição
        linha1 = QHBoxLayout()
        linha1.setSpacing(8)

        self._combo_produto = QComboBox()
        self._combo_produto.setMinimumWidth(220)
        self._combo_produto.currentIndexChanged.connect(self._produto_selecionado)
        linha1.addWidget(self._combo_produto, 2)

        self._descricao = QLineEdit()
        self._descricao.setPlaceholderText("Descrição avulsa (sem produto)")
        self._descricao.setMinimumWidth(150)
        linha1.addWidget(self._descricao, 1)
        layout.addLayout(linha1)

        # Linha 2: Qtd + Dimensões + Unit. + Desc. + Adicionar
        linha2 = QHBoxLayout()
        linha2.setSpacing(8)

        self._qtd = QLineEdit("1")
        self._qtd.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._qtd.setMinimumWidth(60)
        self._qtd.setMaximumWidth(80)
        linha2.addWidget(self._qtd)

        self._dimensoes = QLineEdit()
        self._dimensoes.setPlaceholderText("Dimensões")
        self._dimensoes.setMinimumWidth(100)
        self._dimensoes.setMaximumWidth(140)
        linha2.addWidget(self._dimensoes)

        self._unit = QLineEdit()
        self._unit.setPlaceholderText("Unit. R$")
        self._unit.setMinimumWidth(80)
        self._unit.setMaximumWidth(110)
        linha2.addWidget(self._unit)

        self._desconto = QLineEdit()
        self._desconto.setPlaceholderText("Desc. R$")
        self._desconto.setMinimumWidth(60)
        self._desconto.setMaximumWidth(80)
        linha2.addWidget(self._desconto)

        botao = QPushButton("Adicionar")
        botao.setProperty("role", "primary")
        botao.clicked.connect(self._adicionar)
        botao.setMinimumWidth(100)
        linha2.addWidget(botao)

        remover = QPushButton("Remover Selecionada")
        remover.clicked.connect(self._remover)
        remover.setMinimumWidth(120)
        linha2.addWidget(remover)
        linha2.addStretch(1)
        layout.addLayout(linha2)
        return caixa

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
        }
        self._itens.append(novo)
        self._descricao.clear()
        self._dimensoes.clear()
        self._unit.clear()
        self._desconto.clear()
        self._qtd.setText("1")
        self._atualizar()

    def _remover(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._itens):
            return
        del self._itens[linha]
        self._atualizar()

    def _atualizar(self) -> None:
        self._tabela.preencher(self._linhas_display())
        total = sum(
            (_dec(i["valor_unitario"]) * _dec(i["quantidade"]) - _dec(i["desconto"]))
            for i in self._itens
        )
        self._resumo.setText(
            f"{len(self._itens)} itens • Subtotal: {formatar_moeda(str(total))}"
        )
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
            linhas.append(
                {
                    "seq": f"{seq:02d}",
                    "descricao": descricao,
                    "quantidade": str(item.get("quantidade") or ""),
                    "dimensoes": item.get("dimensoes") or "",
                    "valor_unitario": formatar_moeda(item.get("valor_unitario")),
                    "desconto": formatar_moeda(item.get("desconto")),
                    "valor_total": formatar_moeda(
                        str(
                            _dec(item.get("valor_unitario"))
                            * _dec(item.get("quantidade"))
                            - _dec(item.get("desconto"))
                        )
                    ),
                }
            )
        return linhas

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
        self._atualizar()

    def habilitar(self, ligado: bool) -> None:
        for widget in (
            self._combo_produto,
            self._descricao,
            self._qtd,
            self._dimensoes,
            self._unit,
            self._desconto,
        ):
            widget.setEnabled(ligado)
        for botao in self.findChildren(QPushButton):
            botao.setEnabled(ligado)