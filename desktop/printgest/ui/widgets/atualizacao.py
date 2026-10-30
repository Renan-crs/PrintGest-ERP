"""Widget de notificação de atualização (M3 §3.11).

Baseado em conceitos de UX design de Impeccable e Taste Skill:
- Informação crucial deve ser visível, não esconder em tooltip
- Pop-up não bloqueante para não interromper o fluxo de trabalho
- Ação clara com botão de download
- Fechamento fácil
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QApplication,
)
from PySide6.QtGui import QIcon, QPalette, QColor

from printgest import __version__


class NotificacaoAtualizacao(QWidget):
    """Banner de notificação não bloqueante para atualizações disponíveis.
    
    Aparece no topo da tela principal quando uma versão mais nova é detectada.
    Não impede o uso do sistema (modo leitura opcional).
    """
    
    atualizar_solicitado = Signal(str)  # URL do download
    
    def __init__(self, informacoes: dict, pai=None) -> None:
        super().__init__(pai)
        self._inf = informacoes
        self._visivel = True
        
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Configura a interface do banner de atualização."""
        self.setObjectName("bannerAtualizacao")
        
        # Container principal com fundo amarelo (alerta, não erro)
        container = QWidget()
        container.setObjectName("containerAtualizacao")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(8)
        
        # Linha 1: Título e versão
        linha1 = QHBoxLayout()
        titulo = QLabel(f"Atualização disponível: PrintGest {self._inf['versao_nova']}")
        titulo.setStyleSheet("font-weight: 600; font-size: 14px; color: #1e293b;")
        
        data_label = QLabel(f"• {self._inf.get('data', '')}")
        data_label.setProperty("role", "muted")
        linha1.addWidget(titulo)
        linha1.addWidget(data_label)
        linha1.addStretch(1)
        layout.addLayout(linha1)
        
        # Linha 2: Botão de fechar (X)
        linha2 = QHBoxLayout()
        linha2.addStretch(1)
        
        self._btn_fechar = QPushButton("×")
        self._btn_fechar.setObjectName("btnFecharAtualizacao")
        self._btn_fechar.setFixedSize(24, 24)
        self._btn_fechar.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #64748b;
                font-size: 20px;
            }
            QPushButton:hover {
                color: #475569;
            }
        """)
        self._btn_fechar.clicked.connect(self.esconder)
        linha2.addWidget(self._btn_fechar)
        layout.addLayout(linha2)
        
        # Revisionamento - apenas mostrar as primeiras 3 mudanças
        revisoes = self._inf.get('revisoes', [])[:3]
        if revisoes:
            revisao_label = QLabel("Principais melhorias:")
            revisao_label.setStyleSheet("font-weight: 500; font-size: 13px; color: #334155;")
            layout.addWidget(revisao_label)
            
            self._txt_revisoes = QTextEdit()
            self._txt_revisoes.setReadOnly(True)
            self._txt_revisoes.setFixedHeight(60)
            self._txt_revisoes.setStyleSheet("""
                QTextEdit {
                    background: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 4px;
                    font-size: 12px;
                    padding: 8px;
                }
            """)
            
            texto_revisoes = "\n".join(f"• {r}" for r in revisoes)
            if len(self._inf.get('revisoes', [])) > 3:
                texto_revisoes += f"\n... e mais {len(self._inf.get('revisoes', [])) - 3} melhorias"
            self._txt_revisoes.setPlainText(texto_revisoes)
            layout.addWidget(self._txt_revisoes)
        
        # Linha de ação
        linha_acao = QHBoxLayout()
        linha_acao.addStretch(1)
        
        self._btn_atualizar = QPushButton("Baixar atualização")
        self._btn_atualizar.setObjectName("btnAtualizar")
        self._btn_atualizar.setStyleSheet("""
            QPushButton {
                background: #0f172a;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #1e293b;
            }
        """)
        self._btn_atualizar.clicked.connect(self._ao_atualizar)
        linha_acao.addWidget(self._btn_atualizar)
        
        btn_mais_info = QPushButton("Mais informações")
        btn_mais_info.setObjectName("btnMaisInfo")
        btn_mais_info.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                color: #475569;
            }
            QPushButton:hover {
                background: #f1f5f9;
            }
        """)
        btn_mais_info.clicked.connect(self._ao_mais_info)
        linha_acao.addWidget(btn_mais_info)
        linha_acao.addStretch(1)
        
        layout.addLayout(linha_acao)
        
        # Monta o layout final
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        
        # Aplicar estilo
        self._aplicar_estilo()
    
    def _aplicar_estilo(self) -> None:
        """Aplica os estilos do sistema ao banner."""
        self.setStyleSheet("""
            #bannerAtualizacao {
                background: #fef3c7;
                border-bottom: 1px solid #fcd34d;
            }
            #containerAtualizacao {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
        """)
    
    def _ao_atualizar(self) -> None:
        """Handler para clique no botão de atualização."""
        url = self._inf.get('download_url')
        if url:
            # Em produção, aqui abriria o navegador ou iniciaria o download
            # Por enquanto, emite o sinal para o main window tratar
            self.atualizar_solicitado.emit(url)
            self.esconder()
    
    def _ao_mais_info(self) -> None:
        """Handler para clique em mais informações."""
        # TODO: abrir página de release notes
        pass
    
    def esconder(self) -> None:
        """Esconde o banner."""
        self._visivel = False
        self.hide()
    
    def mostrar(self) -> None:
        """Mostra o banner novamente."""
        self._visivel = True
        self.show()
    
    def esta_visivel(self) -> bool:
        """Retorna se o banner está visível."""
        return self._visivel


def criar_banner_atualizacao(informacoes: dict) -> NotificacaoAtualizacao:
    """Factory function para criar o widget de notificação."""
    return NotificacaoAtualizacao(informacoes)