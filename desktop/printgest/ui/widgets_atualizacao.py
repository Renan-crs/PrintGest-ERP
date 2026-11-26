"""Banner não bloqueante de atualização (Fase 1 — apenas aviso).

Antes este arquivo vivia em `ui/widgets/atualizacao.py`, mas o diretório
colidia com o módulo `ui/widgets.py` e era excluído do bundle. Aqui é um módulo
normal, importável tanto em dev quanto no executável.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from printgest.ui.widgets import estado_muted


class NotificacaoAtualizacao(QWidget):
    """Aviso no topo da tela principal; a ação abre a página da release."""

    atualizar_solicitado = Signal(str)
    instalacao_solicitada = Signal(dict)

    def __init__(self, informacoes: dict, pai=None) -> None:
        super().__init__(pai)
        self._inf = informacoes
        self._visivel = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("bannerAtualizacao")
        self.setAccessibleName("Aviso de atualização")
        container = QWidget()
        container.setObjectName("containerAtualizacao")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)

        linha1 = QHBoxLayout()
        titulo = QLabel(
            f"Atualização disponível: PrintGest {self._inf.get('versao_nova', '')}"
        )
        titulo.setStyleSheet("font-weight: 600; font-size: 14px; color: #1e293b;")
        data_label = QLabel(f"• {self._inf.get('data', '')}")
        estado_muted(data_label)
        linha1.addWidget(titulo)
        linha1.addWidget(data_label)
        linha1.addStretch(1)

        self._btn_fechar = QPushButton("×")
        self._btn_fechar.setObjectName("btnFecharAtualizacao")
        self._btn_fechar.setToolTip("Fechar aviso de atualização")
        self._btn_fechar.setAccessibleName("Fechar aviso de atualização")
        self._btn_fechar.setFixedSize(24, 24)
        self._btn_fechar.clicked.connect(self.esconder)
        linha1.addWidget(self._btn_fechar)
        layout.addLayout(linha1)

        revisoes = list(self._inf.get("revisoes") or [])[:3]
        if revisoes:
            rotulo = QLabel("Principais melhorias:")
            rotulo.setStyleSheet("font-weight: 500; font-size: 13px; color: #334155;")
            layout.addWidget(rotulo)
            texto = QTextEdit()
            texto.setReadOnly(True)
            texto.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # não entra na ordem de Tab
            texto.setAccessibleName("Principais melhorias")
            texto.setFixedHeight(60)
            texto.setPlainText("\n".join(f"• {r}" for r in revisoes))
            layout.addWidget(texto)

        linha_acao = QHBoxLayout()
        linha_acao.addStretch(1)
        self._btn_instalar = QPushButton("&Instalar atualização")
        self._btn_instalar.setObjectName("btnInstalarAtualizacao")
        self._btn_instalar.setToolTip("Baixar e instalar a nova versão (Alt+I)")
        self._btn_instalar.setAccessibleName("Instalar atualização")
        self._btn_instalar.clicked.connect(self._ao_instalar)
        linha_acao.addWidget(self._btn_instalar)

        self._btn_atualizar = QPushButton("&Ver atualização")
        self._btn_atualizar.setObjectName("btnAtualizar")
        self._btn_atualizar.setToolTip("Abrir a página da release (Alt+V)")
        self._btn_atualizar.setAccessibleName("Ver atualização")
        self._btn_atualizar.clicked.connect(self._ao_atualizar)
        linha_acao.addWidget(self._btn_atualizar)
        btn_mais_info = QPushButton("Mais i&nformações")
        btn_mais_info.setObjectName("btnMaisInfo")
        btn_mais_info.setToolTip("Abrir os detalhes da versão (Alt+N)")
        btn_mais_info.setAccessibleName("Mais informações")
        btn_mais_info.clicked.connect(self._ao_atualizar)
        linha_acao.addWidget(btn_mais_info)
        linha_acao.addStretch(1)
        layout.addLayout(linha_acao)

        principal = QVBoxLayout(self)
        principal.setContentsMargins(0, 0, 0, 0)
        principal.addWidget(container)
        self.setStyleSheet(
            "#bannerAtualizacao { background: #fef3c7; "
            "border-bottom: 1px solid #fcd34d; }"
            "#containerAtualizacao { background: white; border-radius: 8px; }"
        )

    def _ao_instalar(self) -> None:
        self.instalacao_solicitada.emit(dict(self._inf))

    def _ao_atualizar(self) -> None:
        url = str(self._inf.get("download_url") or "")
        if url:
            self.atualizar_solicitado.emit(url)

    def esconder(self) -> None:
        self._visivel = False
        self.hide()

    def mostrar(self) -> None:
        self._visivel = True
        self.show()

    def esta_visivel(self) -> bool:
        return self._visivel


def criar_banner_atualizacao(informacoes: dict) -> NotificacaoAtualizacao:
    return NotificacaoAtualizacao(informacoes)
