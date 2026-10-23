"""Tela 1.2 — Ativação de Licença do Sistema (PrintGest ERP).

O usuário digita a **chave de produto** (`XXXX-XXXX-XXXX-XXXX`) entregue na
contratação. O on-premise valida a chave online no RedGest (Contrato C,
`/api/v1/licencas-software/validar/`) e guarda a licença local; a partir daí a
revalidação acontece em segundo plano.
"""

from __future__ import annotations

import re

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

_FORMATO_CHAVE = re.compile(r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")

_PASSOS = [
    ("Chave de Produto", "4 blocos hexadecimais"),
    ("Validação Online", "Confirmação no servidor"),
    ("Sistema Liberado", "Sincronização balcão"),
]


class AtivacaoWindow(QMainWindow):
    """Tela de ativação exibida quando ainda não existe licença associada."""

    ativada = Signal()
    saida = Signal()

    def __init__(self, api: Api, token: str | None = None, contrato: str = "c") -> None:
        super().__init__()
        self._api = api
        self._token = token
        self._contrato_b = (contrato or "c").strip().lower() == "b"
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

        if self._contrato_b:
            subtitulo = QLabel(
                "Informe o CNPJ da empresa e o código da licença enviados pelo "
                "RedGest para liberar o acesso a todas as estações de trabalho da gráfica."
            )
        else:
            subtitulo = QLabel(
                "Digite a chave de produto entregue na contratação do PrintGest para "
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
        if self._contrato_b:
            self._campo_cnpj.setFocus()
        else:
            self._campo_chave.setFocus()

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

        if self._contrato_b:
            form.addWidget(self._rotulo("CNPJ"))
            self._campo_cnpj = QLineEdit()
            self._campo_cnpj.setPlaceholderText("00.000.000/0000-00")
            form.addWidget(self._campo_cnpj)

            form.addWidget(self._rotulo("Código da Licença"))
            self._campo_codigo = QLineEdit()
            self._campo_codigo.setProperty("mono", "true")
            self._campo_codigo.setPlaceholderText("Código enviado pelo RedGest")
            form.addWidget(self._campo_codigo)

            formato = QLabel(
                "Para o Contrato B (RedGest v4.0), informe o CNPJ e o código da "
                "licença. A ativação é online e associa o equipamento à licença."
            )
            formato.setObjectName("subtitulo")
            formato.setWordWrap(True)
            form.addWidget(formato)
        else:
            form.addWidget(self._rotulo("Chave de Produto"))
            self._campo_chave = QLineEdit()
            self._campo_chave.setMaxLength(19)
            self._campo_chave.setProperty("mono", "true")
            self._campo_chave.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
            self._campo_chave.textChanged.connect(self._manter_chave_formatada)
            form.addWidget(self._campo_chave)
            formato = QLabel(
                "A chave tem 16 caracteres hexadecimais (4 blocos de 4, separados por "
                "hífen) e é validada online no servidor de licenças."
            )
            formato.setObjectName("subtitulo")
            formato.setWordWrap(True)
            form.addWidget(formato)

        self._erro = QLabel("")
        self._erro.setProperty("role", "error")
        self._erro.setWordWrap(True)
        form.addWidget(self._erro)

        form.addStretch(1)

        btn_testar = botao_com_atalho("Testar Local API Service")
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
        titulo_m = QLabel("Como funciona o Licenciamento por Chave de Produto")
        titulo_m.setStyleSheet("font-weight: 700;")
        cab_m.addWidget(titulo_m)
        cab_m.addStretch(1)
        modelo_l.addLayout(cab_m)
        modelo_l.addWidget(badge("Tolerância Offline: 72 Horas", "atencao"))
        texto_m = QPlainTextEdit()
        texto_m.setProperty("role", "muted")
        texto_m.setPlainText(
            "A ativação é 100% online: o Local API Service confirma a chave no "
            "servidor de licenças e guarda a licença nesta máquina. A revalidação "
            "roda em segundo plano. Em caso de oscilação ou queda temporária de "
            "internet, o sistema opera normalmente por até 72 horas em tolerância "
            "offline, sem travar vendas no balcão ou emissão de cupons."
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

    @staticmethod
    def _formatar_chave(texto: str) -> str:
        """Normaliza para hexadecimais maiúsculos com hífens a cada 4 caracteres."""
        bruto = "".join(c for c in texto.upper() if c in "0123456789ABCDEF")[:16]
        return "-".join(bruto[i : i + 4] for i in range(0, len(bruto), 4))

    def _manter_chave_formatada(self, texto: str) -> None:
        """Mantém a chave em XXXX-XXXX-XXXX-XXXX sem roubar o cursor (P5)."""
        if not hasattr(self, "_campo_chave"):
            return
        formatado = self._formatar_chave(texto)
        if formatado == texto:
            return
        posicao = self._campo_chave.cursorPosition()
        deslocamento = formatado.count("-") - texto.count("-")
        self._campo_chave.blockSignals(True)
        self._campo_chave.setText(formatado)
        self._campo_chave.blockSignals(False)
        self._campo_chave.setCursorPosition(
            max(0, min(len(formatado), posicao + deslocamento))
        )

    # --------------------------------------------------------------- ações

    def _testar(self) -> None:
        self._botao_testar.setEnabled(False)
        self._status.setText("Testando Local API Service…")

        def ok(resultado) -> None:
            self._botao_testar.setEnabled(True)
            if resultado:
                self._status.setText("● Local API Service respondendo — HTTP 200 OK")
                self._status.setProperty("role", "success")
            else:
                self._status.setText("● Sem resposta do Local API Service — verifique o daemon")
                self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        def erro(_) -> None:
            self._botao_testar.setEnabled(True)
            self._status.setText("● Sem resposta do Local API Service — verifique o daemon")
            self._status.setProperty("role", "error")
            aplicar_estilo(self._status)

        rodar(self._api.testar_comunicacao, ok, erro)

    def _ativar(self) -> None:
        if self._contrato_b:
            cnpj = self._campo_cnpj.text().strip()
            codigo = self._campo_codigo.text().strip()
            if not cnpj:
                self._erro.setText("Informe o CNPJ da empresa.")
                return
            if not codigo:
                self._erro.setText("Informe o código da licença.")
                return
            self._erro.setText("")
            self._marcar_passo(1)
            self._botao_ativar.setEnabled(False)
            self._botao_ativar.setText("Validando online…")

            def chamada():
                return self._api.ativar_licenca(self._token, cnpj=cnpj, codigo=codigo)

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
                self._marcar_passo(0)
                self._erro.setProperty("role", "error")
                self._erro.setText(msg)
                aplicar_estilo(self._erro)

            rodar(chamada, ok, erro)
            return

        chave = self._campo_chave.text().strip().upper()
        if not _FORMATO_CHAVE.match(chave):
            self._erro.setText(
                "Informe a chave de produto completa (XXXX-XXXX-XXXX-XXXX)."
            )
            return

        self._erro.setText("")
        self._marcar_passo(1)
        self._botao_ativar.setEnabled(False)
        self._botao_ativar.setText("Validando online…")

        def chamada():
            return self._api.ativar_licenca(self._token, chave)

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
            self._marcar_passo(0)
            self._erro.setProperty("role", "error")
            self._erro.setText(msg)
            aplicar_estilo(self._erro)

        rodar(chamada, ok, erro)