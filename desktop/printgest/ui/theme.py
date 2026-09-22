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

QLabel#titulo { font-size: 20px; font-weight: 700; }
QLabel#subtitulo { color: %texto-muted%; font-size: 13px; }
QLabel#labelForm { font-size: 11px; font-weight: 700; color: %texto-muted%; text-transform: uppercase; }

QLineEdit {
    background-color: %surface-muted%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    padding: 8px 10px;
    color: %texto%;
    selection-background-color: %primary%;
}
QLineEdit:focus { border: 1px solid %primary%; }
QLineEdit[mono="true"] { font-family: "Consolas"; letter-spacing: 1px; }

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

QStatusBar { background-color: %surface-muted%; color: %texto-muted%; border-top: 1px solid %borda%; }
"""


def aplicar_theme(app: QApplication) -> QApplication:
    app.setFont(QFont(FONT_FAMILY, 10))
    qss = _QSS
    for chave, valor in CORES.items():
        qss = qss.replace(f"%{chave}%", valor)
    app.setStyleSheet(qss)
    return app