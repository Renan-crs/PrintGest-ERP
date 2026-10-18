"""Componentes reutilizáveis das telas 1.x (login, ativação, modo leitura)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)


def aplicar_estilo(widget: QWidget) -> None:
    """Recompila o QSS de `widget` após mudanças de propriedade dinâmica."""
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)


def botao_com_atalho(
    texto: str, atalho: str = "", role: str = ""
) -> tuple[QWidget, QPushButton]:
    """Botão com hint de teclado ao lado (padrão dos mockups Fluent)."""
    caixa = QWidget()
    caixa.setObjectName("botaoKbd")
    layout = QHBoxLayout(caixa)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(6)

    botao = QPushButton(texto)
    if role:
        botao.setProperty("role", role)

    if atalho:
        chave = QLabel(atalho)
        chave.setProperty("kbdHint", "true")
        chave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chave.setFixedHeight(18)
        layout.addWidget(botao, 1)
        layout.addWidget(chave, 0, Qt.AlignmentFlag.AlignRight)
    else:
        layout.addWidget(botao)
    return caixa, botao


def badge(texto: str, estilo: str = "") -> QLabel:
    """Pílula de status estilo mockup (ex.: Tolerância Offline: 72 Horas)."""
    lbl = QLabel(texto)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setProperty("badge", "true")
    if estilo:
        lbl.setProperty("badgeStyle", estilo)
    return lbl


def formatar_datahora(valor: object) -> str:
    """ISO-8601 (com ou sem fuso) do daemon → `dd/mm/aaaa hh:mm` (vazia se nulo)."""
    if not valor:
        return ""
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    return momento.strftime("%d/%m/%Y %H:%M")


class ElideLabel(QLabel):
    """`QLabel` de uma linha que elide o texto quando não couber.

    O texto completo permanece acessível por `text()` e vira tooltip — o
    desenho (paintEvent) é que encurta visualmente. Assim nenhum rótulo do
    dashboard é cortado sem uma forma de ler o valor inteiro.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        # Não impõe a largura do texto: o rótulo pode encolher (elide) para
        # liberar espaço em telas estreitas, sem travar o layout.
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        painter = QPainter(self)
        metrics = self.fontMetrics()
        elidido = metrics.elidedText(
            self.text(), Qt.TextElideMode.ElideRight, max(0, self.width())
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(self.alignment()), elidido)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(evento)
        self._atualizar_tooltip()

    def _atualizar_tooltip(self) -> None:
        completo = self.text()
        cabe = self.fontMetrics().horizontalAdvance(completo) <= max(0, self.width())
        self.setToolTip("" if cabe else completo)


class FlowLayout(QLayout):
    """Layout que dispõe os itens em linhas e reflui quando a largura muda.

    Usado no grid de KPIs do Início: em janelas estreitas os cartões descem de
    linha em vez de serem espremidos (evita truncamento).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        margem: int = 0,
        espaco_h: int = 12,
        espaco_v: int = 12,
    ) -> None:
        super().__init__(parent)
        self._itens: list = []
        self._espaco_h = espaco_h
        self._espaco_v = espaco_v
        self.setContentsMargins(margem, margem, margem, margem)

    def addItem(self, item) -> None:  # noqa: N802 (API Qt)
        self._itens.append(item)

    def count(self) -> int:
        return len(self._itens)

    def itemAt(self, indice: int):  # noqa: N802 (API Qt)
        if 0 <= indice < len(self._itens):
            return self._itens[indice]
        return None

    def takeAt(self, indice: int):  # noqa: N802 (API Qt)
        if 0 <= indice < len(self._itens):
            return self._itens.pop(indice)
        return None

    def expandingDirections(self):  # noqa: N802 (API Qt)
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (API Qt)
        return True

    def heightForWidth(self, largura: int) -> int:  # noqa: N802 (API Qt)
        return self._dispor(QRect(0, 0, largura, 0), aplicar=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (API Qt)
        super().setGeometry(rect)
        self._dispor(rect, aplicar=True)

    def sizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 (API Qt)
        tamanho = QSize()
        for item in self._itens:
            tamanho = tamanho.expandedTo(item.minimumSize())
        margens = self.contentsMargins()
        tamanho += QSize(
            margens.left() + margens.right(), margens.top() + margens.bottom()
        )
        return tamanho

    def _dispor(self, rect: QRect, aplicar: bool) -> int:
        margens = self.contentsMargins()
        x = rect.x() + margens.left()
        y = rect.y() + margens.top()
        limite = rect.right() - margens.right()
        altura_linha = 0
        for item in self._itens:
            hint = item.sizeHint()
            if altura_linha and x + hint.width() > limite:
                x = rect.x() + margens.left()
                y += altura_linha + self._espaco_v
                altura_linha = 0
            if aplicar:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._espaco_h
            altura_linha = max(altura_linha, hint.height())
        return y + altura_linha + margens.bottom() - rect.y()