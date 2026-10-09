"""Tela 1.1 — Acesso ao Sistema (Login)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from printgest import APP_NAME, __version__
from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.widgets import aplicar_estilo, badge, botao_com_atalho

TITULO = "Acesso ao Sistema"


class LoginWindow(QMainWindow):
    """Autentica no Local API Service e emite os dados de sessão."""

    autenticado = Signal(dict)
    saida = Signal()

    def __init__(self, api: Api) -> None:
        super().__init__()
        self._api = api
        self.setWindowTitle(f"PrintGest ERP — {TITULO}")
        self.setMinimumSize(780, 560)

        base = QWidget()
        layout = QVBoxLayout(base)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(12)
        layout.addStretch(1)

        card = QWidget()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 32, 40, 28)
        card_layout.setSpacing(14)

        cabeçalho = QVBoxLayout()
        cabeçalho.setSpacing(6)
        linha_top = QHBoxLayout()
        linha_top.addWidget(badge(f"Build {__version__}", "primary"))
        linha_top.addStretch(1)
        daemon = QLabel("Local API Service: 127.0.0.1:8000")
        daemon.setProperty("role", "muted")
        linha_top.addWidget(daemon)
        cabeçalho.addLayout(linha_top)

        titulo = QLabel(TITULO)
        titulo.setObjectName("titulo")
        cabeçalho.addWidget(titulo)
        subtitulo = QLabel("ERP Desktop para Gráfica Rápida e Comunicação Visual")
        subtitulo.setObjectName("subtitulo")
        cabeçalho.addWidget(subtitulo)
        card_layout.addLayout(cabeçalho)

        self._erro = QLabel("")
        self._erro.setProperty("role", "error")
        self._erro.setWordWrap(True)
        card_layout.addWidget(self._erro)

        self._campo_usuario = self._linha_form(
            card_layout, "Usuário", "seu.usuario", False
        )
        self._campo_senha = self._linha_form(
            card_layout, "Senha", "", True
        )
        self._campo_senha.returnPressed.connect(self._tentar_login)

        self._status = QLabel("")
        self._status.setProperty("role", "muted")
        card_layout.addWidget(self._status)

        card_layout.addSpacing(4)
        btn_entrar = botao_com_atalho(
            "Entrar no Sistema", "F10 / Enter", "primary"
        )
        btn_entrar[1].clicked.connect(self._tentar_login)
        btn_sair = botao_com_atalho("Sair", "Esc")
        btn_sair[1].clicked.connect(self.saida.emit)
        acoes = QHBoxLayout()
        acoes.setSpacing(10)
        acoes.addWidget(btn_entrar[0], 2)
        acoes.addWidget(btn_sair[0], 1)
        card_layout.addLayout(acoes)

        matricula = QLabel("Entre com as credenciais fornecidas pela gerência.")
        matricula.setProperty("role", "muted")
        matricula.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(matricula)

        layout.addWidget(card)
        layout.addStretch(1)

        status_bar = self.statusBar()
        status_bar.showMessage(f"Local API Service: {self._api.base_url_display}")

        self.setCentralWidget(base)
        self._botao_entrar = btn_entrar[1]
        self._botao_sair = btn_sair[1]

        QShortcut(QKeySequence(Qt.Key.Key_F10), self, self._tentar_login)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.saida.emit)

        self._verificar_daemon()

    @staticmethod
    def _linha_form(layout, rotulo: str, placeholder: str, senha: bool):
        label = QLabel(rotulo.upper())
        label.setObjectName("labelForm")
        layout.addWidget(label)
        campo = QLineEdit()
        campo.setPlaceholderText(placeholder)
        campo.setClearButtonEnabled(True)
        if senha:
            campo.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(campo)
        return campo

    def _verificar_daemon(self) -> None:
        def checar():
            return self._api.testar_comunicacao()

        def ok(_) -> None:
            self._status.setText("● Local API Service respondendo (online)")
            self._status.setProperty("role", "success")
            aplicar_estilo(self._status)

        def erro(msg: str) -> None:
            self._status.setText("● Local API Service sem resposta — verifique o daemon")
            self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        rodar(checar, ok, erro)

    def _tentar_login(self) -> None:
        usuario = self._campo_usuario.text().strip()
        senha = self._campo_senha.text()
        if not (usuario and senha):
            self._erro.setText("Informe usuário e senha.")
            self._campo_usuario.setFocus()
            return

        self._erro.setText("")
        self._bloquear_form(True)

        def chamada():
            return self._api.login(usuario, senha)

        def ok(dados: dict) -> None:
            self._bloquear_form(False)
            self.autenticado.emit(dados)

        def erro(msg: str) -> None:
            self._bloquear_form(False)
            self._erro.setText(msg)
            self._campo_senha.setFocus()
            self._campo_senha.selectAll()

        rodar(chamada, ok, erro)

    def _bloquear_form(self, bloqueado: bool) -> None:
        self._botao_entrar.setEnabled(not bloqueado)
        if bloqueado:
            self._erro.setProperty("role", "error")
            self._erro.setText("Autenticando…")
            aplicar_estilo(self._erro)