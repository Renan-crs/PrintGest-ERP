"""Campo de busca rápida com debounce e atalho F2 (padrão dos mockups).

Dispara `buscado(texto)` ~250ms após a última digitação — evita spam de
requests a cada tecla no daemon local.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

from printgest.ui.widgets import aplicar_estilo

PAUSA_MS = 250


class CampoBusca(QWidget):
    buscado = Signal(str)

    def __init__(
        self, placeholder: str = "Buscar...", nivel_hint: str = "F2"
    ) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._entrada = QLineEdit()
        self._entrada.setPlaceholderText(placeholder)
        self._entrada.setClearButtonEnabled(True)
        layout.addWidget(self._entrada, 1)

        hint = QLabel(nivel_hint)
        hint.setProperty("kbdHint", "true")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint, 0)

        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(PAUSA_MS)
        self._temporizador.timeout.connect(self._publicar)
        self._entrada.textChanged.connect(self._agendar)

        self._atalho = QShortcut(QKeySequence(nivel_hint), self)
        self._atalho.activated.connect(self.focar)
        self.setFocusProxy(self._entrada)

    def focar(self) -> None:
        self._entrada.setFocus()
        self._entrada.selectAll()
        aplicar_estilo(self)

    def _agendar(self) -> None:
        self._temporizador.start()

    def _publicar(self) -> None:
        self.buscado.emit(self._entrada.text().strip())

    def texto(self) -> str:
        return self._entrada.text().strip()