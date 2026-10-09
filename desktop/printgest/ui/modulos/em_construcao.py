"""Página placeholder para módulos do menu ainda não implementados.

Substituída conforme cada tela do §1 de `docs/telas_e_fluxos.md` for entregue.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PaginaEmConstrucao(QWidget):
    def __init__(self, rotulo: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)

        titulo = QLabel(rotulo)
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)

        nota = QLabel(
            "Módulo em construção. Esta tela será habilitada nas próximas etapas "
            "conforme o plano de desenvolvimento do PrintGest."
        )
        nota.setObjectName("subtitulo")
        nota.setWordWrap(True)
        layout.addWidget(nota)
        layout.addStretch(1)