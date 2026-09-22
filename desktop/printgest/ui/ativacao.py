"""Tela 1.2 — Ativação de Licença do Sistema (PrintGest ERP).

Troca CNPJ + código de licença RedGest por uma licença ativa (`online_periodic`).
Em caso de sucesso, o on-premise cria a licença local e o token passa a ser
renovado automaticamente em segundo plano.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.widgets import aplicar_estilo, badge, botao_com_atalho

_PASSOS = [
    ("Empresa & Chave", "Identificação fiscal"),
    ("Validação RedGest", "Handshake & Token"),
    ("Sistema Liberado", "Sincronização balcão"),
]


class AtivacaoWindow(QMainWindow):
    """Tela de ativação exibida quando ainda não existe licença associada."""

    ativada = Signal()
    saida = Signal()

    def __init__(self, api: Api, token: str | None = None, cnpj_atual: str | None = None) -> None:
        super().__init__()
        self._api = api
        self._token = token
        self._cnpj_atual = cnpj_atual
        self.setWindowTitle("PrintGest ERP — Ativação de Licença do Sistema")
        self.setMinimumSize(960, 640)

        base = QWidget()
        layout = QVBoxLayout(base)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(14)

        cabeçalho = QVBoxLayout()
        cabeçalho.setSpacing(4)
        linha_badge = QHBoxLayout()
        linha_badge.addWidget(badge("Setup Inicial", "primary"))
        linha_badge.addStretch(1)
        protocolo = QLabel("PRD-2.0 / §3.REDGEST")
        protocolo.setProperty("mono", "true")
        protocolo.setProperty("role", "muted")
        linha_badge.addWidget(protocolo)
        cabeçalho.addLayout(linha_badge)

        titulo = QLabel("Ativação de Licença do Sistema — PrintGest ERP")
        titulo.setObjectName("titulo")
        cabeçalho.addWidget(titulo)

        subtitulo = QLabel(
            "Informe os dados de licenciamento contratados junto ao RedGest para "
            "liberar o acesso a todas as estações de trabalho da gráfica."
        )
        subtitulo.setObjectName("subtitulo")
        subtitulo.setWordWrap(True)
        cabeçalho.addWidget(subtitulo)
        layout.addLayout(cabeçalho)

        layout.addWidget(self._stepper())

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._painel_form(), 3)
        corpo.addWidget(self._painel_info(), 2)
        layout.addLayout(corpo)

        self.setCentralWidget(base)
        QShortcut(QKeySequence(Qt.Key.Key_F10), self, self._ativar)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.saida.emit)
        self._campo_codigo.setFocus()

    # ------------------------------------------------------------------ helpers

    def _stepper(self) -> QWidget:
        caixa = QWidget()
        painel = QHBoxLayout(caixa)
        painel.setContentsMargins(0, 0, 0, 4)
        painel.setSpacing(8)
        self._passos_labels: list[QWidget] = []
        for indice, (titulo, subtitulo) in enumerate(_PASSOS):
            item = QVBoxLayout()
            item.setSpacing(2)
            cab = QHBoxLayout()
            cab.addWidget(QLabel(str(indice + 1)))
            titulo_lbl = QLabel(titulo)
            cab.addWidget(titulo_lbl)
            cab.addStretch(1)
            item.addLayout(cab)
            desc = QLabel(subtitulo)
            desc.setObjectName("subtitulo")
            item.addWidget(desc)
            bloco = QWidget()
            bloco.setLayout(item)
            bloco.setObjectName("passo")
            self._passos_labels.append(bloco)
            painel.addWidget(bloco, 1)
            if indice < len(_PASSOS) - 1:
                barra = QWidget()
                barra.setFixedHeight(1)
                barra.setObjectName("divider")
                painel.addWidget(barra, 0)
        painel.addItem(QSpacerItem(10, 1, QSizePolicy.Policy.Expanding))
        self._passo_atual = 0
        self._marcar_passo(0)
        return caixa

    def _marcar_passo(self, indice: int) -> None:
        self._passo_atual = indice
        for i, bloco in enumerate(self._passos_labels):
            ativo = i <= indice
            bloco.setProperty("passoAtivo", ativo)
            aplicar_estilo(bloco)

    def _painel_form(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)

        form.addWidget(self._rotulo("CNPJ"))
        self._campo_cnpj = QLineEdit()
        self._campo_cnpj.setInputMask("99.999.999/9999-99;_")
        if self._cnpj_atual:
            self._campo_cnpj.setText(self._cnpj_atual)
        self._campo_cnpj.setPlaceholderText("00.000.000/0000-00")
        form.addWidget(self._campo_cnpj)

        form.addWidget(self._rotulo("Código de Licença"))
        self._campo_codigo = QLineEdit()
        self._campo_codigo.setMaxLength(25)
        self._campo_codigo.setProperty("mono", "true")
        self._campo_codigo.setPlaceholderText("PGST-XXXX-XXXX-XXXX-XXXX")
        self._campo_codigo.textChanged.connect(
            lambda t: self._campo_codigo.setText(t.upper())
            if t != t.upper()
            else None
        )
        form.addWidget(self._campo_codigo)
        formato = QLabel("Formato padrão: PGST-XXXX-XXXX-XXXX-XXXX (25 caracteres alfanuméricos)")
        formato.setObjectName("subtitulo")
        formato.setWordWrap(True)
        form.addWidget(formato)

        self._erro = QLabel("")
        self._erro.setProperty("role", "error")
        self._erro.setWordWrap(True)
        form.addWidget(self._erro)

        form.addStretch(1)

        btn_testar = botao_com_atalho("Testar Comunicação com RedGest")
        btn_testar[1].clicked.connect(self._testar)
        btn_ativar = botao_com_atalho("Validar e Ativar Licença Online", "F10", "primary")
        btn_ativar[1].clicked.connect(self._ativar)
        btn_sair = botao_com_atalho("Sair", "Esc")
        btn_sair[1].clicked.connect(self.saida.emit)

        ativacao = QHBoxLayout()
        ativacao.setSpacing(10)
        ativacao.addWidget(btn_testar[0], 1)
        ativacao.addWidget(btn_ativar[0], 2)
        form.addLayout(ativacao)
        form.addWidget(btn_sair[0])

        self._botao_ativar = btn_ativar[1]
        self._botao_testar = btn_testar[1]
        return card

    def _painel_info(self) -> QWidget:
        painel = QVBoxLayout()
        painel.setSpacing(12)

        nodo = QWidget()
        nodo.setObjectName("cardLow")
        nodo_l = QVBoxLayout(nodo)
        nodo_l.setContentsMargins(16, 14, 16, 14)
        nodo_l.setSpacing(6)
        cab = QHBoxLayout()
        nodo_titulo = QLabel("Função de Nó da Estação de Trabalho")
        nodo_titulo.setStyleSheet("font-weight: 700;")
        cab.addWidget(nodo_titulo)
        cab.addWidget(badge("HOST PRINCIPAL", "primary"))
        cab.addStretch(1)
        nodo_l.addLayout(cab)
        texto_nodo = QPlainTextEdit()
        texto_nodo.setProperty("role", "muted")
        texto_nodo.setPlainText(
            "Esta máquina atuará como Servidor Local "
            "(Local API Service + PostgreSQL embarcado) atendendo até 5 estações "
            "locais simultâneas de balcão e produção."
        )
        texto_nodo.setReadOnly(True)
        texto_nodo.setMaximumHeight(84)
        nodo_l.addWidget(texto_nodo)
        painel.addWidget(nodo)

        modelo = QWidget()
        modelo.setObjectName("card")
        modelo_l = QVBoxLayout(modelo)
        modelo_l.setContentsMargins(16, 14, 16, 14)
        modelo_l.setSpacing(8)
        cab_m = QHBoxLayout()
        titulo_m = QLabel("Como funciona o Modelo de Licenciamento Híbrido RedGest")
        titulo_m.setStyleSheet("font-weight: 700;")
        cab_m.addWidget(titulo_m)
        cab_m.addStretch(1)
        modelo_l.addLayout(cab_m)
        modelo_l.addWidget(badge("Tolerância Offline: 72 Horas", "atencao"))
        texto_m = QPlainTextEdit()
        texto_m.setProperty("role", "muted")
        texto_m.setPlainText(
            "A ativação é 100% online vinculada ao CNPJ da sua gráfica. O Local API "
            "Service renova o token automaticamente em segundo plano. Em caso de "
            "oscilação ou queda temporária de internet, o sistema opera normalmente "
            "por até 72 horas em tolerância offline contínua, sem travar vendas no "
            "balcão ou emissão de cupons."
        )
        texto_m.setReadOnly(True)
        texto_m.setMaximumHeight(132)
        modelo_l.addWidget(texto_m)
        painel.addWidget(modelo)

        ping = QWidget()
        ping.setObjectName("cardLow")
        ping_l = QHBoxLayout(ping)
        ping_l.setContentsMargins(16, 10, 16, 10)
        self._status = QLabel("Endpoint: 127.0.0.1:8000/health (não testado)")
        self._status.setProperty("role", "muted")
        ping_l.addWidget(self._status)
        ping_l.addStretch(1)
        painel.addWidget(ping)

        painel.addStretch(1)
        wrapper = QWidget()
        wrapper.setLayout(painel)
        return wrapper

    @staticmethod
    def _rotulo(texto: str) -> QLabel:
        label = QLabel(texto.upper())
        label.setObjectName("labelForm")
        return label

    # --------------------------------------------------------------- ações

    def _testar(self) -> None:
        self._botao_testar.setEnabled(False)
        self._status.setText("Testando comunicação com RedGest…")

        def ok(_) -> None:
            self._botao_testar.setEnabled(True)
            self._status.setText("● RedGest respondendo — HTTP 200 OK")
            self._status.setProperty("role", "success")
            aplicar_estilo(self._status)

        def erro(_) -> None:
            self._botao_testar.setEnabled(True)
            self._status.setText("● Sem resposta do RedGest — verifique a conexão")
            self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        rodar(self._api.testar_comunicacao, ok, erro)

    def _ativar(self) -> None:
        cnpj = self._campo_cnpj.text().strip()
        codigo = self._campo_codigo.text().strip()
        if len(cnpj) < 14 or len(codigo) < 8:
            self._erro.setText("Informe o CNPJ completo e o código de licença.")
            return

        self._erro.setText("")
        self._botao_ativar.setEnabled(False)
        self._botao_ativar.setText("Validando com RedGest…")

        def chamada():
            return self._api.ativar_licenca(self._token, cnpj, codigo)

        def ok(_) -> None:
            self._botao_ativar.setEnabled(True)
            self._botao_ativar.setText("Validar e Ativar Licença Online")
            self._marcar_passo(2)
            self._erro.setProperty("role", "success")
            self._erro.setText("Licença ativada! Carregando o sistema…")
            aplicar_estilo(self._erro)
            self.ativada.emit()

        def erro(msg: str) -> None:
            self._botao_ativar.setEnabled(True)
            self._botao_ativar.setText("Validar e Ativar Licença Online")
            self._marcar_passo(1)
            self._erro.setProperty("role", "error")
            self._erro.setText(msg)
            aplicar_estilo(self._erro)

        rodar(chamada, ok, erro)