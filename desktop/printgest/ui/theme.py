"""Tema do PrintGest — tokens do design system `fluent_print_erp/DESIGN.md`.

Paleta M3/Fluent (janela clara)+ usada nos mockups e no QSS do PySide6. Os
componentes usam `setProperty("role", ...)`: `primary`, `ghost`, `danger`,
`amber` para botões; `label-error` para mensagens; `banner-amber` para o modo
leitura.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

FONT_FAMILY = "Inter"

CORES = {
    "canvas": "#F1F5F9",
    "surface": "#FFFFFF",
    "surface-muted": "#F8FAFC",
    "borda": "#E2E8F0",
    "borda-forte": "#CBD5E1",
    "texto": "#0F172A",
    "texto-muted": "#475569",
    "primary": "#2563EB",
    "primary-hover": "#1D4ED8",
    "primary-active": "#1E40AF",
    "on-primary": "#FFFFFF",
    "tertiary": "#8B5CF6",
    "sucesso": "#059669",
    "sucesso-container": "#ECFDF5",
    "atencao": "#D97706",
    "atencao-container": "#FFFBEB",
    "atencao-borda": "#FDE68A",
    "erro": "#DC2626",
    "erro-container": "#FEF2F2",
    "erro-borda": "#FECACA",
    "focus": "#2563EB",
}

_QSS = """
* {
    font-family: "Inter";
    font-size: 13px;
    color: %texto%;
}

QWidget {
    background-color: %canvas%;
}

QWidget#botaoKbd, QWidget#cardBaixo { background: transparent; }

QWidget#passo { background-color: %surface-muted%; border: 1px solid %borda%; border-radius: 6px; }
QWidget#passo[passoAtivo="true"] { background-color: #EFF6FF; border: 1px solid %primary%; }

QPlainTextEdit { background: transparent; border: none; color: %texto-muted%; font-size: 12px; }

QLabel[badge] {
    font-size: 11px;
    font-weight: 700;
    border-radius: 4px;
    padding: 2px 8px;
    letter-spacing: 0.02em;
    background-color: %surface-muted%;
    color: %texto-muted%;
    border: 1px solid %borda-forte%;
}
QLabel[badgeStyle="primary"] { background-color: #DBE1FF; color: #003EA8; border-color: #B4C5FF; }
QLabel[badgeStyle="success"] { background-color: %sucesso-container%; color: %sucesso%; border-color: #A7F3D0; }
QLabel[badgeStyle="atencao"] { background-color: %atencao-container%; color: %atencao%; border-color: %atencao-borda%; }
QLabel[badgeStyle="erro"] { background-color: %erro-container%; color: %erro%; border-color: %erro-borda%; }

QWidget#card {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 10px;
}

QWidget#cardLow {
    background-color: %surface-muted%;
    border-radius: 8px;
}

QLabel { background: transparent; color: %texto%; }
QLabel[role="muted"] { color: %texto-muted%; }
QLabel[role="error"] { color: %erro%; font-weight: 600; }
QLabel[role="success"] { color: %sucesso%; font-weight: 600; }
QLabel[role="atencao"] { color: %atencao%; font-weight: 600; }

/* Indicadores clicáveis (licença/servidor) e links de card. */
QPushButton[role="success"], QPushButton[role="atencao"], QPushButton[role="error"] {
    border: none;
    background: transparent;
    font-weight: 700;
    padding: 2px 6px;
}
QPushButton[role="success"] { color: %sucesso%; }
QPushButton[role="atencao"] { color: %atencao%; }
QPushButton[role="error"] { color: %erro%; }
QPushButton[role="success"]:hover,
QPushButton[role="atencao"]:hover,
QPushButton[role="error"]:hover { background-color: %surface-muted%; }

QLabel#titulo { font-size: 20px; font-weight: 700; }
QLabel#subtitulo { color: %texto-muted%; font-size: 13px; }
QLabel#labelForm { font-size: 11px; font-weight: 700; color: %texto-muted%; text-transform: uppercase; }

QLineEdit, QDateEdit, QTimeEdit, QSpinBox, QDoubleSpinBox {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 22px;
    color: %texto%;
    selection-background-color: %primary%;
}
QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %primary%;
}
QLineEdit[mono="true"] { font-family: "Consolas"; letter-spacing: 1px; }
/* Controles sem setas próprias de incremento (o usuário digita os valores). */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: none; }

/* Combos no mesmo desenho dos campos (sem o "artefato" do estilo nativo do
   Windows). A seta fica a nativa: em versionamentos recentes do Qt o truque de
   "triângulo por bordas" em `::down-arrow` vira um bloco preto (G6). */
QComboBox {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 22px;
    color: %texto%;
}
QComboBox:focus, QComboBox:on { border: 1px solid %primary%; }
QComboBox QAbstractItemView {
    background-color: %surface%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    color: %texto%;
    outline: none;
    selection-background-color: %primary%;
    selection-color: %on-primary%;
}

QPushButton {
    background: transparent;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
    color: %texto%;
}
QPushButton:hover { background-color: %surface-muted%; border-color: %primary%; }
QPushButton:pressed { background-color: %borda%; }

QPushButton[role="primary"] {
    background-color: %primary%;
    border: none;
    color: %on-primary%;
}
QPushButton[role="primary"]:hover { background-color: %primary-hover%; }
QPushButton[role="primary"]:pressed { background-color: %primary-active%; }
QPushButton[role="primary"]:disabled { background-color: %borda%; color: %texto-muted%; }

QPushButton[role="danger"] {
    background: %surface-muted%;
    border: 1px solid %erro-borda%;
    color: %erro%;
}
QPushButton[role="danger"]:hover { background-color: %erro-container%; }

QPushButton[role="amber"] {
    background-color: %atencao%;
    border: none;
    color: #FFFFFF;
    font-weight: 700;
}
QPushButton[role="amber"]:hover { background-color: #B45309; }

QPushButton[kbd="true"] { padding-right: 6px; }

QLabel[kbdHint="true"] {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 4px;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 5px;
}

QWidget#bannerAmber {
    background-color: %atencao-container%;
    border-bottom: 1px solid %atencao-borda%;
}

QFrame#divider { background-color: %borda%; }

QScrollArea { background: transparent; border: none; }

/* Scrollbars finas, sem setas — evita o visual clássico do Windows (B1). */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: %borda-forte%;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: %texto-muted%; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: %borda-forte%;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background-color: %texto-muted%; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QStatusBar { background-color: %surface-muted%; color: %texto-muted%; border-top: 1px solid %borda%; }

/* ------------------------------------------------------- tela principal */

QWidget#cabecalho { background-color: %surface%; border-bottom: 1px solid %borda%; }
QLabel#marca { font-size: 16px; font-weight: 800; color: %primary%; }
QLineEdit#buscaGlobal {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    color: %texto%;
    padding: 6px 12px;
}
QLineEdit#buscaGlobal:focus { border: 1px solid %primary%; }
QListWidget#sugestoesBusca {
    background-color: %surface%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    color: %texto%;
    padding: 4px;
}
QListWidget#sugestoesBusca::item { padding: 4px 8px; border-radius: 4px; }
QListWidget#sugestoesBusca::item:selected { background-color: %primary%; color: %on-primary%; }
QLabel#valorCard { font-size: 18px; font-weight: 800; color: %texto%; }
QProgressBar {
    border: 1px solid %borda-forte%;
    border-radius: 4px;
    background-color: %surface-muted%;
}
QProgressBar::chunk { background-color: %primary%; border-radius: 4px; }

QWidget#sidebar { background-color: %surface%; border-right: 1px solid %borda%; }
QLabel#grupoMenu {
    color: %texto-muted%;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    /* padding-left 5px + o inset interno do QLabel alinham o rótulo ao texto
       dos itens (QPushButton[nav]) — ver B4. */
    padding: 10px 5px 4px 5px;
}
QPushButton[nav="true"] {
    border: none;
    border-radius: 6px;
    color: %texto-muted%;
    font-weight: 600;
    padding: 7px 10px;
    text-align: left;
}
QPushButton[nav="true"]:hover { background-color: %surface-muted%; color: %texto%; }
QPushButton[nav="true"]:checked { background-color: #EFF6FF; color: %primary%; }

QLabel#bannerLeitura {
    background-color: %atencao-container%;
    border: 1px solid %atencao-borda%;
    border-radius: 8px;
    color: %atencao%;
    font-weight: 600;
    padding: 8px 12px;
}

QLabel#bannerErro {
    background-color: %erro-container%;
    border: 1px solid %erro-borda%;
    border-radius: 8px;
    color: %erro%;
    font-weight: 600;
    padding: 8px 12px;
}

QToolButton#menuUsuario {
    background-color: %surface%;
    border: 1px solid %borda-forte%;
    border-radius: 16px;
    color: %texto%;
    font-weight: 600;
    padding: 4px 10px;
}
QToolButton#menuUsuario:hover { border-color: %primary%; background-color: %surface-muted%; }
QToolButton#menuUsuario::menu-indicator { image: none; width: 0; }

QPushButton[icone="true"] {
    border: none;
    background: transparent;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 15px;
    color: %texto-muted%;
}
QPushButton[icone="true"]:hover { background-color: %surface-muted%; color: %texto%; }

QPushButton[link="true"] {
    border: none;
    background: transparent;
    color: %primary%;
    font-weight: 600;
    padding: 2px 0;
    text-align: left;
}
QPushButton[link="true"]:hover { color: %primary-hover%; }

QPushButton[chave="true"] {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 12px;
}
QPushButton[chave="true"]:hover { border-color: %primary%; color: %texto%; }
QPushButton[chave="true"]:checked { background-color: %primary%; border-color: %primary%; color: #FFFFFF; }

/* Controle segmentado (visões/filtros) — mesmo visual, por objectName. */
QPushButton#chaveRapida {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
}
QPushButton#chaveRapida:hover { border-color: %primary%; color: %texto%; }
QPushButton#chaveRapida:checked { background-color: %primary%; border-color: %primary%; color: #FFFFFF; }

/* Quadro Kanban (Projetos) — uma coluna por etapa, cartões sem corte. */
QScrollArea#areaQuadro { background: transparent; border: none; }
QFrame#colunaKanban {
    background-color: %surface-muted%;
    border: 1px solid %borda%;
    border-radius: 10px;
}
QLabel#tituloColunaKanban {
    font-size: 11px;
    font-weight: 700;
    color: %texto-muted%;
    letter-spacing: 0.04em;
}
QLabel#contagemKanban {
    background-color: %surface%;
    border: 1px solid %borda-forte%;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 700;
    padding: 1px 8px;
}
QFrame#cartaoKanban {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 8px;
}
QFrame#cartaoKanban:hover { border-color: %primary%; }
QFrame#cartaoKanban:focus { border: 2px solid %primary%; }
QLabel#tituloCartao { font-weight: 700; }

/* Botão de ação compacto dentro de uma linha da grade (ex.: Cancelar). */
QPushButton#acaoLinha {
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 5px;
}

QLabel#secaoForm {
    color: %primary%;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding-top: 8px;
}

QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: transparent;
    font-size: 13px;
    selection-background-color: #EFF6FF;
    selection-color: %texto%;
}
QTableWidget::item {
    border-bottom: 1px solid %borda%;
    padding: 6px 8px;
    border-left: 3px solid transparent;
}
QTableWidget::item:selected { border-left: 3px solid %primary%; }
QTableWidget::item:hover { background-color: %surface-muted%; }
QHeaderView::section {
    background-color: %surface-muted%;
    border: none;
    border-bottom: 1px solid %borda-forte%;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 700;
    padding: 6px 8px;
}
QTableCornerButton::section { background-color: %surface-muted%; border: none; }

QLabel#vazioTabela {
    background: transparent;
    color: %texto-muted%;
    font-size: 13px;
    padding: 12px;
}

QPushButton#pagBotao {
    border: 1px solid %borda-forte%;
    background-color: %surface-muted%;
    border-radius: 5px;
    color: %texto%;
    font-weight: 700;
    padding: 0;
}
QPushButton#pagBotao:hover { border-color: %primary%; color: %primary%; }
QPushButton#pagBotao:disabled { color: %borda-forte%; border-color: %borda%; }

QPushButton[role="ghost"] { border: none; color: %texto-muted%; }
QPushButton[role="ghost"]:hover { color: %erro%; background-color: %erro-container%; }

QWidget#rodape { background-color: %surface%; border-top: 1px solid %borda%; }
"""


def aplicar_theme(app: QApplication) -> QApplication:
    app.setFont(QFont(FONT_FAMILY, 10))
    qss = _QSS
    for chave, valor in CORES.items():
        qss = qss.replace(f"%{chave}%", valor)
    app.setStyleSheet(qss)
    return app