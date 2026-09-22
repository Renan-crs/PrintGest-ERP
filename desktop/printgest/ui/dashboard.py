"""Tela principal (Dashboard) — placeholder até as telas dos módulos 2.x+.

Quando o usuário opta por continuar em modo consulta, exibe um banner superior
de aviso e restringe as ações de escrita.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from printgest.ui.widgets import badge


class DashboardWindow(QMainWindow):
    def __init__(self, modo_leitura: bool = False) -> None:
        super().__init__()
        self._modo_leitura = modo_leitura
        self.setWindowTitle("PrintGest ERP — Painel Principal")
        self.setMinimumSize(1000, 640)

        base = QWidget()
        layout = QVBoxLayout(base)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if modo_leitura:
            layout.addWidget(self._banner())

        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(24, 20, 24, 16)
        conteudo.setSpacing(12)
        conteudo.addWidget(self._titulo())
        conteudo.addStretch(1)
        layout.addLayout(conteudo)
        self.setCentralWidget(base)

    def _banner(self) -> QWidget:
        banner = QWidget()
        banner.setObjectName("bannerAmber")
        linha = QHBoxLayout(banner)
        linha.setContentsMargins(24, 8, 24, 8)
        linha.setSpacing(10)
        titulo = QLabel("Sistema em modo leitura — apenas consultas")
        titulo.setStyleSheet("font-weight: 700; font-size: 13px;")
        linha.addWidget(titulo)
        linha.addWidget(badge("Escritas bloqueadas", "atencao"))
        linha.addStretch(1)
        linha.addWidget(QLabel("[F9] Sincronizar agora"))
        return banner

    def _titulo(self) -> QWidget:
        caixa = QWidget()
        layout = QVBoxLayout(caixa)
        layout.setSpacing(4)
        titulo = QLabel("Painel Principal — PrintGest ERP")
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)
        subtitulo = QLabel(
            "Fase 0 (skeleton). As próximas telas do Balcão, Cadastros e Produção "
            "substituirão este painel à medida que forem habilitadas."
        )
        subtitulo.setObjectName("subtitulo")
        subtitulo.setWordWrap(True)
        layout.addWidget(subtitulo)
        return caixa