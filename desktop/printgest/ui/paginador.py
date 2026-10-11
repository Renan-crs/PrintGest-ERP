"""Paginador ágil do rodapé da grade (mockup 2.1): info + navegação 1ª/←/→/última."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from printgest.ui.widgets import ElideLabel

LOTE = 50


class Paginador(QWidget):
    mudou = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._info = ElideLabel()
        self._info.setProperty("role", "muted")
        layout.addWidget(self._info, 1)

        self._primeira = self._botao("|‹")
        self._anterior = self._botao("‹")
        self._pagina = ElideLabel("Pág 1 de 1")
        self._pagina.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._proxima = self._botao("›")
        self._ultima = self._botao("›|")

        for botao in (self._primeira, self._anterior, self._proxima, self._ultima):
            layout.addWidget(botao)
        layout.addWidget(self._pagina)

        self._total = 0
        self._offset = 0

        self._primeira.clicked.connect(lambda: self._ir(0))
        self._anterior.clicked.connect(lambda: self._ir(self._offset - LOTE))
        self._proxima.clicked.connect(lambda: self._ir(self._offset + LOTE))
        self._ultima.clicked.connect(self._ultima_pagina)

    @staticmethod
    def _botao(texto: str) -> QPushButton:
        botao = QPushButton(texto)
        botao.setObjectName("pagBotao")
        botao.setFixedSize(26, 26)
        return botao

    def atualizar(self, total: int, offset: int = 0, limit: int = LOTE) -> None:
        self._total = total
        self._offset = offset
        inicio = offset + 1 if total else 0
        fim = min(offset + limit, total)
        self._info.setText(
            f"Exibindo {inicio}–{fim} de {total} "
            + ("registro" if total == 1 else "registros")
        )
        total_paginas = max((total + limit - 1) // limit, 1)
        pagina_atual = min(offset // limit + 1, total_paginas)
        self._pagina.setText(f"Pág {pagina_atual} de {total_paginas}")
        self._primeira.setEnabled(offset > 0)
        self._anterior.setEnabled(offset > 0)
        self._proxima.setEnabled(fim < total)
        self._ultima.setEnabled(fim < total)

    def _ir(self, offset: int) -> None:
        offset = max(0, min(offset, max(self._total - LOTE, 0)))
        if offset != self._offset:
            self.mudou.emit(offset)

    def _ultima_pagina(self) -> None:
        resto = self._total % LOTE
        ultimo = self._total - (resto if resto else LOTE)
        self._ir(max(ultimo, 0))