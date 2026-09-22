"""Componentes reutilizáveis das telas 1.x (login, ativação, modo leitura)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

ROLES_BOTAO_PRIMARIO = "primary"


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