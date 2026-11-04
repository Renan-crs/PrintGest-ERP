"""Tela 1.1 — Acesso ao Sistema (Login)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printgest import APP_NAME, __version__
from printgest.core.api import Api, ApiError
from printgest.core.tarefas import rodar
from printgest.ui.widgets import aplicar_estilo, badge, botao_com_atalho, estado_sucesso, estado_erro, estado_muted

TITULO = "Acesso ao Sistema"


class PrimeiroAcessoDialog(QDialog):
    """Define a senha de um login em primeiro acesso.

    Serve tanto para o administrador de uma instalação nova (login `admin`,
    criado sem senha) quanto para funcionários cadastrados pela gerência.
    """

    def __init__(self, api: Api, login: str = "", parent=None) -> None:
        super().__init__(parent)
        self._api = api
        self._sessao: dict | None = None
        self.setWindowTitle("Primeiro acesso — definir senha")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        titulo = QLabel("Primeiro acesso")
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)

        ajuda = QLabel(
            "Use o login informado pela gerência (na primeira instalação, o "
            "login é admin). Defina a senha agora; ela precisa ter ao menos "
            "8 caracteres."
        )
        ajuda.setWordWrap(True)
        estado_muted(ajuda)
        layout.addWidget(ajuda)

        self._erro = QLabel("")
        estado_erro(self._erro)
        self._erro.setWordWrap(True)
        layout.addWidget(self._erro)

        self._campo_login = self._linha(layout, "Login", "seu.usuario", False)
        self._campo_login.setText(login)
        self._campo_nova = self._linha(layout, "Nova senha", "", True)
        self._campo_confirmar = self._linha(
            layout, "Confirmar nova senha", "", True
        )
        self._campo_confirmar.returnPressed.connect(self._definir)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        cancelar, self._btn_cancelar = botao_com_atalho("Cancelar", "Esc")
        definir, self._btn_definir = botao_com_atalho(
            "Definir senha e entrar", "", "primary"
        )
        self._btn_cancelar.clicked.connect(self.reject)
        self._btn_definir.clicked.connect(self._definir)
        acoes.addWidget(cancelar)
        acoes.addWidget(definir)
        layout.addLayout(acoes)

        (self._campo_nova if login else self._campo_login).setFocus()

    @property
    def sessao(self) -> dict | None:
        """Sessão devolvida pelo backend quando a senha é definida."""
        return self._sessao

    @staticmethod
    def _linha(layout, rotulo: str, placeholder: str, senha: bool) -> QLineEdit:
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

    def _definir(self) -> None:
        login = self._campo_login.text().strip()
        nova = self._campo_nova.text()
        confirmar = self._campo_confirmar.text()

        if not login:
            self._erro.setText("Informe o login.")
            self._campo_login.setFocus()
            return
        if len(nova) < 8:
            self._erro.setText("A senha precisa ter ao menos 8 caracteres.")
            self._campo_nova.setFocus()
            return
        if nova != confirmar:
            self._erro.setText("As senhas não conferem.")
            self._campo_confirmar.setFocus()
            self._campo_confirmar.selectAll()
            return

        self._erro.setText("")
        self._bloquear(True)

        def ok(dados: dict) -> None:
            self._sessao = dados
            self.accept()

        def erro(msg: str) -> None:
            self._bloquear(False)
            self._erro.setText(msg)
            self._campo_login.setFocus()
            self._campo_login.selectAll()

        rodar(lambda: self._api.primeiro_acesso(login, nova), ok, erro)

    def _bloquear(self, bloqueado: bool) -> None:
        for campo in (
            self._campo_login,
            self._campo_nova,
            self._campo_confirmar,
            self._btn_cancelar,
            self._btn_definir,
        ):
            campo.setEnabled(not bloqueado)
        if bloqueado:
            self._erro.setText("Definindo senha…")


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
        estado_muted(daemon)
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
        estado_erro(self._erro)
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
        estado_muted(self._status)
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

        self._btn_primeiro_acesso = QPushButton(
            "Primeiro acesso — definir senha"
        )
        self._btn_primeiro_acesso.setProperty("link", "true")
        self._btn_primeiro_acesso.clicked.connect(self._abrir_primeiro_acesso)
        card_layout.addWidget(
            self._btn_primeiro_acesso, alignment=Qt.AlignmentFlag.AlignCenter
        )

        matricula = QLabel(
            "Entre com as credenciais fornecidas pela gerência. "
            "No primeiro acesso, defina sua senha pelo botão acima."
        )
        estado_muted(matricula)
        matricula.setWordWrap(True)
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
            estado_sucesso(self._status)

        def erro(msg: str) -> None:
            self._status.setText("● Local API Service sem resposta — verifique o daemon")
            estado_erro(self._status)

        rodar(checar, ok, erro)

    def _tentar_login(self) -> None:
        usuario = self._campo_usuario.text().strip()
        senha = self._campo_senha.text()
        if not usuario:
            self._erro.setText("Informe o usuário.")
            self._campo_usuario.setFocus()
            return
        if not senha:
            self._erro.setText(
                "Informe a senha. Se este é seu primeiro acesso, clique em "
                "\"Primeiro acesso — definir senha\"."
            )
            self._campo_senha.setFocus()
            return

        self._erro.setText("")
        self._bloquear_form(True)

        def chamada():
            try:
                return {"sessao": self._api.login(usuario, senha)}
            except ApiError as exc:
                # 407 = login existe, mas a senha ainda não foi definida.
                if exc.status_code == 407:
                    return {"primeiro_acesso": usuario}
                raise

        def ok(resultado: dict) -> None:
            self._bloquear_form(False)
            if resultado.get("primeiro_acesso"):
                self._abrir_primeiro_acesso(resultado["primeiro_acesso"])
                return
            self.autenticado.emit(resultado["sessao"])

        def erro(msg: str) -> None:
            self._bloquear_form(False)
            self._erro.setText(msg)
            self._campo_senha.setFocus()
            self._campo_senha.selectAll()

        rodar(chamada, ok, erro)

    def _abrir_primeiro_acesso(self, login: str = "") -> None:
        if not login:
            login = self._campo_usuario.text().strip()
        dialogo = PrimeiroAcessoDialog(self._api, login, self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.sessao:
            self.autenticado.emit(dialogo.sessao)

    def _bloquear_form(self, bloqueado: bool) -> None:
        self._botao_entrar.setEnabled(not bloqueado)
        self._btn_primeiro_acesso.setEnabled(not bloqueado)
        if bloqueado:
            estado_erro(self._erro)
            self._erro.setText("Autenticando…")
            aplicar_estilo(self._erro)