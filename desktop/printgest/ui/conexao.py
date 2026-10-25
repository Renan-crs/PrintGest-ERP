"""Tela 1.3 — Conectar ao Servidor (modo Estação).

Estação é a instalação que usa o Local API Service de OUTRA máquina (a
servidora da gráfica, que guarda o banco e a licença). O instalador da estação
define `PRINTGEST_API_URL` apontando para o servidor; esta tela permite
ajustar/testar o endereço antes do login.

O gate de serial não existe aqui (D6): a licença pertence ao servidor, que já
responde pelo modo de leitura quando algo não está em ordem.

Mesma linguagem da tela de ativação: coluna única de 560 px, botões com
rótulo >= 40 px, erro junto do campo, Esc com confirmação, F10 conecta.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api, base_url_padrao
from printgest.core.tarefas import rodar
from printgest.ui.widgets import EtiquetaQuebra, aplicar_estilo, marca_printgest

_CHAVE_ENDERECO = "servidor/endereco"


def normalizar_endereco(texto: str) -> str:
    """"192.168.0.10:8000/" → "http://192.168.0.10:8000"."""
    endereco = (texto or "").strip()
    if not endereco:
        return ""
    if "://" not in endereco:
        endereco = f"http://{endereco}"
    return endereco.rstrip("/")


class ConexaoWindow(QMainWindow):
    """Endereço do servidor + teste, antes do login (modo Estação)."""

    conectado = Signal(str)  # endereço normalizado
    saida = Signal()

    def __init__(
        self,
        ajustes: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._ajustes = ajustes or QSettings("PrintGest", "PrintGest ERP")
        self._validando = False
        self._tentativa = 0
        self.setWindowTitle("PrintGest ERP — Conectar ao servidor")
        self.setMinimumSize(960, 640)

        base = QWidget()
        externa = QVBoxLayout(base)
        externa.setContentsMargins(48, 40, 48, 24)
        externa.addStretch(3)

        bloco = QWidget()
        bloco.setMaximumWidth(560)
        coluna = QVBoxLayout(bloco)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(8)

        coluna.addWidget(marca_printgest(), 0, Qt.AlignmentFlag.AlignHCenter)
        coluna.addSpacing(8)
        titulo = QLabel("Conectar ao servidor")
        titulo.setObjectName("tituloAtivacao")
        coluna.addWidget(titulo)
        subtitulo = EtiquetaQuebra("Informe o endereço do servidor da sua gráfica.")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        coluna.addWidget(subtitulo)
        coluna.addWidget(self._cartao())
        coluna.addLayout(self._rodape())
        coluna.addSpacing(4)
        nota = EtiquetaQuebra(
            "O sistema e o banco de dados ficam no servidor da gráfica."
        )
        nota.setObjectName("ajudaCampo")
        nota.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        coluna.addWidget(nota)
        externa.addWidget(bloco, 0, Qt.AlignmentFlag.AlignHCenter)
        externa.addStretch(4)

        self.setCentralWidget(base)

        QShortcut(QKeySequence(Qt.Key.Key_F10), self, self._conectar)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._solicitar_saida)
        self._campo.setFocus()
        self._testar()

    # ------------------------------------------------------------- cartão

    def _cartao(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        corpo = QVBoxLayout(card)
        corpo.setContentsMargins(24, 24, 24, 24)
        corpo.setSpacing(4)

        rotulo = QLabel("Endereço do servidor")
        rotulo.setObjectName("rotuloCampo")
        corpo.addWidget(rotulo)
        self._campo = self._campo_endereco()
        self._campo.returnPressed.connect(self._conectar)
        self._erro_campo = self._rotulo_erro()
        corpo.addWidget(self._campo)
        corpo.addWidget(self._erro_campo)
        corpo.addSpacing(24)

        ajuda = EtiquetaQuebra(
            "Este computador é uma estação de trabalho. Use o endereço da "
            "máquina servidora da gráfica (ex.: 192.168.0.10:8000)."
        )
        ajuda.setObjectName("ajudaCampo")
        ajuda.setAccessibleName("Ajuda: endereço do servidor da gráfica")
        corpo.addWidget(ajuda)

        self._erro = EtiquetaQuebra("")
        self._erro.setObjectName("erroCampo")
        corpo.addWidget(self._erro)

        corpo.addStretch(1)
        acoes = QHBoxLayout()
        acoes.setSpacing(8)
        self._botao_sair = self._botao("Sair (Esc)", plano="flat")
        self._botao_sair.clicked.connect(self._solicitar_saida)
        acoes.addWidget(self._botao_sair)
        acoes.addStretch(1)
        self._botao_testar = self._botao("Testar conexão", plano="secondary")
        self._botao_testar.clicked.connect(self._testar)
        acoes.addWidget(self._botao_testar)
        self._botao_conectar = self._botao("Conectar (F10)", plano="primary")
        self._botao_conectar.clicked.connect(self._conectar)
        acoes.addWidget(self._botao_conectar)
        corpo.addLayout(acoes)
        return card

    def _campo_endereco(self) -> QLineEdit:
        ed = QLineEdit()
        ed.setPlaceholderText("192.168.0.10:8000")
        ed.setProperty("formAtivacao", "true")
        ed.setMinimumHeight(40)
        ed.setAccessibleName("Endereço do servidor")
        paleta = ed.palette()
        paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor("#6E6E73"))
        ed.setPalette(paleta)

        inicial = str(self._ajustes.value(_CHAVE_ENDERECO, ""))
        if not inicial:
            inicial = base_url_padrao()
        ed.setText(inicial)
        return ed

    @staticmethod
    def _rotulo_erro() -> QLabel:
        lbl = EtiquetaQuebra("")
        lbl.setObjectName("erroCampo")
        lbl.hide()
        return lbl

    @staticmethod
    def _botao(texto: str, plano: str = "") -> QPushButton:
        b = QPushButton(texto)
        b.setMinimumHeight(40)
        b.setAccessibleName(texto)
        if plano == "primary":
            b.setProperty("role", "primary")
        elif plano == "secondary":
            b.setProperty("role", "secondary")
        else:
            b.setObjectName("botaoFlat")
        return b

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setContentsMargins(4, 12, 4, 0)
        rodape.setSpacing(10)
        self._status = QLabel("Servidor: testando…")
        self._status.setObjectName("statusServidor")
        rodape.addWidget(self._status)
        rodape.addStretch(1)
        return rodape

    # ------------------------------------------------------------ validação

    @staticmethod
    def _provar(endereco: str) -> bool:
        """`GET /health` contra o endereço; cliente efêmero sempre fechado."""
        api = Api(base_url=endereco)
        try:
            return api.testar_comunicacao()
        finally:
            api.fechar()

    def _validar(self) -> bool:
        endereco = normalizar_endereco(self._campo.text())
        if not endereco:
            self._erro_campo.setText("Informe o endereço do servidor.")
            self._erro_campo.show()
            self._campo.setFocus()
            return False
        self._erro_campo.hide()
        self._erro_campo.setText("")
        return True

    def _testar(self) -> None:
        if not self._validar():
            return
        self._botao_testar.setEnabled(False)
        self._status.setText("Servidor: testando…")
        self._status.setProperty("role", "")
        aplicar_estilo(self._status)

        def ok(resultado) -> None:
            self._botao_testar.setEnabled(True)
            if resultado:
                self._status.setText("Servidor: conectado")
                self._status.setProperty("role", "success")
            else:
                self._status.setText("Servidor: sem resposta")
                self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        def erro(_) -> None:
            self._botao_testar.setEnabled(True)
            self._status.setText("Servidor: sem resposta")
            self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        endereco = normalizar_endereco(self._campo.text())
        rodar(lambda: self._provar(endereco), ok, erro)

    # ------------------------------------------------------------ conectar

    def _conectar(self) -> None:
        if self._validando:
            return
        if not self._validar():
            return
        endereco = normalizar_endereco(self._campo.text())
        self._validando = True
        self._tentativa += 1
        tentativa = self._tentativa
        self._erro.setText("")
        self._botao_conectar.setEnabled(False)
        self._botao_conectar.setText("Conectando…")
        self._status.setText("Servidor: testando…")

        def ok(resultado) -> None:
            if tentativa != self._tentativa:
                return
            self._validando = False
            self._botao_conectar.setEnabled(True)
            self._botao_conectar.setText("Conectar (F10)")
            if not resultado:
                self._status.setText("Servidor: sem resposta")
                self._status.setProperty("role", "error")
                aplicar_estilo(self._status)
                self._erro.setText(
                    "Não foi possível conectar — confira o endereço e se o "
                    "servidor está ligado."
                )
                return
            self._ajustes.setValue(_CHAVE_ENDERECO, endereco)
            self._ajustes.sync()
            self.close()  # o roteador assume a partir daqui
            self.conectado.emit(endereco)

        def erro(msg: str) -> None:
            if tentativa != self._tentativa:
                return
            self._validando = False
            self._botao_conectar.setEnabled(True)
            self._botao_conectar.setText("Conectar (F10)")
            self._status.setText("Servidor: sem resposta")
            self._status.setProperty("role", "error")
            aplicar_estilo(self._status)
            self._erro.setText(msg)

        rodar(lambda: self._provar(endereco), ok, erro)

    # ---------------------------------------------------------------- saída

    def _solicitar_saida(self) -> None:
        if self._validando:
            return
        resposta = QMessageBox.question(
            self,
            "Sair do PrintGest",
            "Sair do PrintGest sem conectar ao servidor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.saida.emit()
