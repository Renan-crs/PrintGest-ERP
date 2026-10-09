"""Tela 1.3 — Modo Leitura (renovação de licença pendente).

Exibida quando a licença existe mas o token não pôde ser renovado dentro da
tolerância offline. O usuário pode tentar renovar (`F5`), seguir no modo
consulta ou acionar o suporte.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.widgets import aplicar_estilo, badge, botao_com_atalho

_PODERES = [
    ("Visualizar histórico de Ordens de Serviço existentes",
     "Consulte status de produção, prazos de entrega e itens em andamento."),
    ("Consultar estoque, tabelas de preços e clientes",
     "Busca rápida por insumos (papéis, lonas, tintas) e telefones cadastrados."),
    ("Emitir relatórios gerenciais e 2ª via de comprovantes",
     "Reimpressão de fichas técnicas e exportação de relatórios para PDF."),
    ("Visualizar extrato de caixa e fluxo financeiro",
     "Leitura de recebíveis passados, totalizadores de turno e conferência."),
]

_BLOQUEIOS = [
    ("Abertura de novas Ordens de Serviço e Orçamentos",
     "Não é possível gerar novo número de serviço até restabelecer a conexão."),
    ("Finalização de Vendas no Balcão (PDV)",
     "Lançamento de itens rápidos e recebimento em dinheiro/cartão bloqueados."),
    ("Emissão de notas fiscais (NF-e / NFC-e)",
     "Comunicação com SEFAZ suspensa por ausência de token autenticado."),
    ("Alterações cadastrais e movimentação de estoque",
     "Entrada de novos lotes de papel e edição de cadastros indisponíveis."),
]


class ModoLeituraWindow(QMainWindow):
    """Aviso de modo leitura com revalidação de licença."""

    renovada = Signal()
    consulta = Signal()
    saida = Signal()

    def __init__(
        self, api: Api, token: str | None = None, cnpj: str | None = None
    ) -> None:
        super().__init__()
        self._api = api
        self._token = token
        self.setWindowTitle("PrintGest ERP — Sistema em Modo Leitura")
        self.setMinimumSize(1020, 720)

        base = QWidget()
        layout = QVBoxLayout(base)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._banner())
        conteudo = QVBoxLayout()
        conteudo.setContentsMargins(24, 16, 24, 12)
        conteudo.setSpacing(14)
        conteudo.addWidget(self._cabecalho())
        conteudo.addLayout(self._colunas())
        conteudo.addLayout(self._diagnostico())
        conteudo.addLayout(self._acoes())
        conteudo.addStretch(1)
        layout.addLayout(conteudo)

        self.setCentralWidget(base)
        QShortcut(QKeySequence(Qt.Key.Key_F5), self, self._renovar)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.saida.emit)

    # ------------------------------------------------------------------ helpers

    def _banner(self) -> QWidget:
        banner = QWidget()
        banner.setObjectName("bannerAmber")
        linha = QHBoxLayout(banner)
        linha.setContentsMargins(24, 8, 24, 8)
        linha.setSpacing(10)

        titulo = QLabel("SISTEMA EM MODO LEITURA")
        titulo.setStyleSheet("font-weight: 700; font-size: 15px;")
        linha.addWidget(titulo)
        linha.addWidget(badge("Tolerância Offline Expirada", "atencao"))
        linha.addStretch(1)

        btn_revalidar = botao_com_atalho("Revalidar", "F5", "amber")
        btn_revalidar[1].clicked.connect(self._renovar)
        linha.addWidget(btn_revalidar[0])
        self._botao_revalidar = btn_revalidar[1]
        return banner

    def _cabecalho(self) -> QWidget:
        caixa = QWidget()
        linha = QVBoxLayout(caixa)
        linha.setSpacing(6)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        titulo = QLabel("Modo Leitura Ativado — Renovação Pendente")
        titulo.setObjectName("titulo")
        topo.addWidget(titulo)
        topo.addWidget(badge("Offline > 72h", "erro"))
        topo.addStretch(1)
        linha.addLayout(topo)

        self._mensagem = QLabel(
            "A licença RedGest está ativa, porém o token não foi renovado dentro da "
            "tolerância offline. As operações de escrita e emissão fiscal estão "
            "suspensas até a próxima sincronização bem-sucedida."
        )
        self._mensagem.setObjectName("subtitulo")
        self._mensagem.setWordWrap(True)
        linha.addWidget(self._mensagem)

        return caixa

    def _colunas(self) -> QHBoxLayout:
        colunas = QHBoxLayout()
        colunas.setSpacing(14)
        colunas.addWidget(self._lista("pode"), 1)
        colunas.addWidget(self._lista("bloqueio"), 1)
        return colunas

    def _lista(self, tipo: str) -> QWidget:
        pode = tipo == "pode"
        card = QWidget()
        card.setObjectName("card")
        lista = QVBoxLayout(card)
        lista.setContentsMargins(18, 16, 18, 16)
        lista.setSpacing(8)

        cab = QHBoxLayout()
        titulo = QLabel(
            "O que você PODE fazer agora" if pode else "O que está SUSPENSO temporariamente"
        )
        titulo.setStyleSheet("font-weight: 700; font-size: 15px;")
        cab.addWidget(titulo)
        cab.addStretch(1)
        lista.addLayout(cab)
        lista.addWidget(
            badge("4 Ações Ativas", "success") if pode else badge("4 Bloqueios", "erro")
        )
        texto = QLabel(
            "Liberado para consulta e conferência"
            if pode else "Requer revalidação de licença"
        )
        texto.setObjectName("subtitulo")
        lista.addWidget(texto)

        for titulo_item, descricao in (_PODERES if pode else _BLOQUEIOS):
            item = QWidget()
            item.setObjectName("cardLow")
            item_l = QVBoxLayout(item)
            item_l.setContentsMargins(12, 10, 12, 10)
            item_l.setSpacing(2)
            nome = QLabel(titulo_item)
            nome.setStyleSheet("font-weight: 600;")
            nome.setWordWrap(True)
            item_l.addWidget(nome)
            detalhe = QLabel(descricao)
            detalhe.setObjectName("subtitulo")
            detalhe.setWordWrap(True)
            item_l.addWidget(detalhe)
            lista.addWidget(item)

        lista.addStretch(1)
        return card

    def _diagnostico(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(14)

        card = QWidget()
        card.setObjectName("cardLow")
        diag = QVBoxLayout(card)
        diag.setContentsMargins(16, 12, 16, 12)
        diag.setSpacing(6)
        titulo = QLabel("DIAGNÓSTICO DE CONECTIVIDADE")
        titulo.setObjectName("labelForm")
        diag.addWidget(titulo)
        self._diag_texto = QPlainTextEdit()
        self._diag_texto.setPlainText(
            "Status da Internet na máquina servidora: a renovação automática não "
            "obteve resposta do RedGest na última tentativa. Clique em \"Verificar "
            "Rede Local\" para conferir a conectividade do daemon; quando a "
            "internet/serviço voltar, o sistema retoma o funcionamento normal."
        )
        self._diag_texto.setReadOnly(True)
        self._diag_texto.setMaximumHeight(84)
        diag.addWidget(self._diag_texto)
        linha.addWidget(card, 1)

        btn_rede = botao_com_atalho("Verificar Rede Local (127.0.0.1)")
        btn_rede[1].clicked.connect(self._verificar_rede)
        linha.addWidget(btn_rede[0], 0)
        return linha

    def _acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(10)

        btn_renovar = botao_com_atalho("Tentar Renovar Agora", "F5", "primary")
        btn_renovar[1].clicked.connect(self._renovar)
        btn_consulta = botao_com_atalho("Continuar em Modo Consulta", "Enter")
        btn_consulta[1].clicked.connect(self.consulta.emit)
        btn_suporte = botao_com_atalho("Contatar Suporte / Financeiro RedGest", "F1", "danger")
        btn_suporte[1].clicked.connect(self._suporte)

        self._botao_renovar = btn_renovar[1]
        linha.addWidget(btn_suporte[0], 1)
        linha.addWidget(btn_consulta[0], 1)
        linha.addWidget(btn_renovar[0], 2)
        return linha

    # --------------------------------------------------------------- ações

    def _renovar(self) -> None:
        self._botao_renovar.setEnabled(False)
        self._botao_revalidar.setEnabled(False)
        self._mensagem.setText("Tentando renovar a licença com o RedGest…")
        self._mensagem.setProperty("role", "muted")
        aplicar_estilo(self._mensagem)

        def chamada():
            return self._api.renovar_licenca(self._token)

        def ok(_) -> None:
            self._mensagem.setProperty("role", "success")
            self._mensagem.setText("Licença renovada! Retornando ao funcionamento normal…")
            aplicar_estilo(self._mensagem)
            self.renovada.emit()

        def erro(msg: str) -> None:
            self._botao_renovar.setEnabled(True)
            self._botao_revalidar.setEnabled(True)
            self._mensagem.setProperty("role", "error")
            self._mensagem.setText(
                f"Não foi possível renovar agora: {msg}. O sistema permanece em modo "
                "leitura — novas tentativas acontecem automaticamente."
            )
            aplicar_estilo(self._mensagem)

        rodar(chamada, ok, erro)

    def _verificar_rede(self) -> None:
        self._diag_texto.setPlainText(
            "Verificando conectividade com o Local API Service (127.0.0.1:8000)…"
        )

        def ok(resultado) -> None:
            if resultado:
                self._diag_texto.setPlainText(
                    "Rede local OK — daemon respondendo em 127.0.0.1:8000. "
                    "A pendência está na comunicação com o RedGest (internet)."
                )
            else:
                self._diag_texto.setPlainText(
                    "Falha ao contatar o daemon em 127.0.0.1:8000. "
                    "Verifique se o Local API Service está em execução."
                )

        def erro(_) -> None:
            self._diag_texto.setPlainText(
                "Falha ao contatar o daemon em 127.0.0.1:8000. "
                "Verifique se o Local API Service está em execução."
            )

        rodar(self._api.testar_comunicacao, ok, erro)

    def _suporte(self) -> None:
        self._mensagem.setProperty("role", "muted")
        self._mensagem.setText(
            "Canais de atendimento RedGest: WhatsApp Financeiro e Central 0800 "
            "(Opção 2 — Licenciamento). Consulte o contrato para os canais oficiais."
        )
        aplicar_estilo(self._mensagem)