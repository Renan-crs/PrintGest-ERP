"""Tema do PrintGest — linguagem visual inspirada no Apple Design.

Adota os fundamentos de *Principles of Great Design* / *The Details of UI
Typography* (WWDC) para o desktop Qt:

- **Grays** do sistema Apple (janela clara): fundo ``systemGray6``, hairlines
  ``separator``, texto ``label``/``secondaryLabel`` — separação por fio de cabelo,
  não por blocos pesados (§12 materiais, §16 craft).
- **Azul de sistema** ``#0071E3`` como acento; verde/laranja/vermelho nas versões
  legíveis para texto sobre branco.
- **Tipografia óptica (§15):** títulos com *tracking* negativo, rótulos pequenos
  com tracking levemente positivo, hierarquia por peso+tamanho — nunca só por
  tamanho. ``text-transform`` não existe no QSS; o maiúsculo vem do Python.
- **Cantos contínuos** aproximados por raios consistentes (controles 6px, cartões
  e diálogos 12px, pílulas 999px).

Os componentes continuam usando ``setProperty("role", ...)``: ``primary``,
``ghost``, ``danger``, ``amber`` para botões; ``label-error`` para mensagens;
``banner-amber`` para o modo leitura e o banner de tolerância. O movimento vive
em ``animacao.py``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

FONT_FAMILY = "Inter"

# Resolução da família na inicialização: se "Inter" não estiver instalada, o
# Qt faz um fallback por widget (cabeçalhos de tabela podiam cair numa serifa
# enquanto o corpo ficava sans — achado nº 8 da revisão do PDV). Fixamos UMA
# família real para o app inteiro; no Windows, "Segoe UI" sempre existe.
# Preguiçosa: QFontDatabase exige um QGuiApplication vivo (chamar no import
# derrubava o processo antes do `app` existir).
FONT_RESOLVIDA = FONT_FAMILY


def _resolver_familia() -> str:
    try:
        familias = QFontDatabase.families()
    except Exception:  # noqa: BLE001 — sem banco de fontes: fica a hint sans
        return FONT_FAMILY
    if not familias:  # plataforma offscreen: sem fontes, usa a hint sans
        return FONT_FAMILY
    if FONT_FAMILY in familias:
        return FONT_FAMILY
    return "Segoe UI" if "Segoe UI" in familias else familias[0]

_ASSETS = Path(__file__).resolve().parent / "assets"

CORES = {
    # --- superfícies (janela clara do macOS)
    "canvas": "#F5F5F7",          # systemGray6 — fundo de janela
    "surface": "#FFFFFF",         # cartões, barras, campos
    "surface-muted": "#F5F5F7",   # hovers/repouso de controles
    # --- traços
    "borda": "#D8D8DC",           # separador (hairline)
    "borda-forte": "#C7C7CC",     # systemGray3
    # --- texto
    "texto": "#1D1D1F",           # label
    "texto-muted": "#6E6E73",     # secondaryLabel
    # --- acento
    "primary": "#0071E3",         # azul de sistema
    "primary-hover": "#0077ED",
    "primary-active": "#0068C8",
    "primary-container": "#EAF3FF",  # tint de seleção
    "on-primary": "#FFFFFF",
    "tertiary": "#AF52DE",        # roxo de sistema
    # --- estados
    # verde legível. `#248A3D` sobre branco dava 4,40:1 — abaixo do 4,5:1 exigido
    # para texto normal. `#1B7031` sobe para 4,80:1 no branco e 4,55:1 sobre o
    # próprio container (badges), mantendo a mesma família de verde.
    "sucesso": "#1B7031",         # verde legível
    "sucesso-container": "#E3F3E7",
    "atencao": "#B25000",         # laranja legível
    "atencao-hover": "#93400A",
    "atencao-container": "#FFF4E8",
    "atencao-borda": "#F3C99A",
    "erro": "#D70015",            # vermelho de sistema
    "erro-container": "#FCEEEE",
    "erro-borda": "#F2B8BC",
    "focus": "#0071E3",
    # Revisão da tela de ativação (out/2026): texto de ação sobre o canvas
    # (4,34:1 do primary ficava abaixo de 4,5:1) e borda de campo >= 3:1.
    "acao": "#0066CC",           # links/botões de texto sobre canvas (5,1:1)
    "borda-campo": "#8E8E93",     # borda de campo da ativação (3,3:1 no branco)
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

QWidget#botaoKbd, QWidget#cardBaixo, QWidget#caixaForma { background: transparent; }

QWidget#passo { background-color: %surface-muted%; border: 1px solid %borda%; border-radius: 6px; }
QWidget#passo[passoAtivo="true"] { background-color: %primary-container%; border: 1px solid %primary%; }

QPlainTextEdit { background: transparent; border: none; color: %texto-muted%; font-size: 12px; }

/* Selos: pílula cheia, sem contorno pesado (§16 simplicidade). */
QLabel[badge] {
    font-size: 11px;
    font-weight: 600;
    border-radius: 999px;
    padding: 2px 9px;
    letter-spacing: 0.01em;
    background-color: %surface-muted%;
    color: %texto-muted%;
    border: none;
}
QLabel[badgeStyle="primary"] { background-color: %primary-container%; color: %primary%; }
QLabel[badgeStyle="success"] { background-color: %sucesso-container%; color: %sucesso%; }
QLabel[badgeStyle="atencao"] { background-color: %atencao-container%; color: %atencao%; }
QLabel[badgeStyle="erro"] { background-color: %erro-container%; color: %erro%; }

/* Cartões: material claro com fio de cabelo; nada de sombras duras. */
QWidget#card {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 12px;
}

QWidget#cardLow {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 12px;
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
    font-weight: 600;
    padding: 2px 6px;
}
QPushButton[role="success"] { color: %sucesso%; }
QPushButton[role="atencao"] { color: %atencao%; }
QPushButton[role="error"] { color: %erro%; }
QPushButton[role="success"]:hover,
QPushButton[role="atencao"]:hover,
QPushButton[role="error"]:hover { background-color: %surface-muted%; border-radius: 6px; }

/* Tipografia óptica: tracking negativo no título, neutro no corpo (§15). */
QLabel#titulo { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }
QLabel#subtitulo { color: %texto-muted%; font-size: 13px; }
QLabel#labelForm { font-size: 11px; font-weight: 600; color: %texto-muted%; letter-spacing: 0.02em; }

QLineEdit, QDateEdit, QTimeEdit, QSpinBox, QDoubleSpinBox {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 22px;
    color: %texto%;
    selection-background-color: %primary%;
    selection-color: %on-primary%;
}
QLineEdit:hover, QDateEdit:hover, QTimeEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: %borda-forte%;
}
QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid %primary%;
}
QLineEdit[mono="true"] { font-family: "Consolas"; letter-spacing: 1px; }
/* Controles sem setas próprias de incremento (o usuário digita os valores). */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; border: none; }

/* Combos no mesmo desenho dos campos (sem o "artefato" do estilo nativo do
    Windows). A seta nativa renderizava uma barra escura vertical nesta
    versão do Qt (revisão PDV nº 6): virou SVG embutido, como o contra-ícone. */
QComboBox {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 22px;
    color: %texto%;
}
QComboBox:hover { border-color: %borda-forte%; }
QComboBox:focus, QComboBox:on { border: 1px solid %primary%; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(%asset_seta%); width: 11px; height: 7px; }
QComboBox QAbstractItemView {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 8px;
    padding: 4px;
    color: %texto%;
    outline: none;
    selection-background-color: %primary%;
    selection-color: %on-primary%;
}

/* Botões: contorno fino + preenchimento sutil (padrão do macOS). A resposta ao
   toque é imediata no `:pressed` (§1); nada de esperar o release. */
QPushButton {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
    color: %texto%;
}
QPushButton:hover { background-color: %surface-muted%; border-color: %borda-forte%; }
QPushButton:pressed { background-color: %borda%; }

QPushButton[role="primary"] {
    background-color: %primary%;
    border: 1px solid %primary%;
    color: %on-primary%;
}
QPushButton[role="primary"]:hover { background-color: %primary-hover%; border-color: %primary-hover%; }
QPushButton[role="primary"]:pressed { background-color: %primary-active%; border-color: %primary-active%; }
QPushButton[role="primary"]:disabled { background-color: %surface-muted%; border-color: %borda%; color: %texto-muted%; }

/* Ação secundária: mesma forma do primário, sem o preenchimento de acento —
   subordinação clara sem virar um botão "fantasma" difícil de achar. */
QPushButton[role="secondary"] {
    background-color: %surface%;
    border: 1px solid %borda-forte%;
    color: %texto%;
    font-weight: 600;
}
QPushButton[role="secondary"]:hover { background-color: %surface-muted%; border-color: %texto-muted%; }

QPushButton[role="danger"] {
    background: %surface%;
    border: 1px solid %erro-borda%;
    color: %erro%;
}
QPushButton[role="danger"]:hover { background-color: %erro-container%; border-color: %erro%; }

QPushButton[role="amber"] {
    background-color: %atencao%;
    border: 1px solid %atencao%;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton[role="amber"]:hover { background-color: %atencao-hover%; border-color: %atencao-hover%; }

QPushButton[kbd="true"] { padding-right: 6px; }

QLabel[kbdHint="true"] {
    background-color: %surface-muted%;
    border: 1px solid %borda%;
    border-radius: 5px;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 600;
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
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: %borda-forte%;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: %texto-muted%; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: %borda-forte%;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background-color: %texto-muted%; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QStatusBar { background-color: %surface%; color: %texto-muted%; border-top: 1px solid %borda%; }

/* --------------------------------------------------- controles nativos (sem
   isto, QCheckBox/QRadioButton/QMenu/QToolTip caíam no estilo do Windows) */

QCheckBox, QRadioButton {
    spacing: 8px;
    background: transparent; /* sem faixa cinza atrás (revisão PDV nº 5) */
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid %borda-forte%;
    background-color: %surface%;
}
QCheckBox::indicator { border-radius: 5px; }
QRadioButton::indicator { border-radius: 999px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %primary%; }
QCheckBox::indicator:checked {
    background-color: %primary%;
    border-color: %primary%;
    image: url("%asset_check%");
}
QRadioButton::indicator:checked {
    background-color: %primary%;
    border-color: %primary%;
    image: url("%asset_ponto%");
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background-color: %surface-muted%;
    border-color: %borda%;
}
QCheckBox:disabled, QRadioButton:disabled { color: %texto-muted%; }

QMenu {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    background: transparent;
    border-radius: 6px;
    padding: 6px 22px 6px 12px;
}
QMenu::item:selected { background-color: %primary%; color: %on-primary%; }
QMenu::item:disabled { color: %texto-muted%; }
QMenu::separator { height: 1px; background-color: %borda%; margin: 4px 8px; }

QToolTip {
    background-color: %surface%;
    color: %texto%;
    border: 1px solid %borda-forte%;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}

QDialog, QMessageBox { background-color: %surface%; }
QMessageBox QLabel { color: %texto%; }
QDialogButtonBox QPushButton { min-width: 88px; }

/* ------------------------------------------------------- tela principal */

QWidget#cabecalho { background-color: %surface%; border-bottom: 1px solid %borda%; }
QLabel#marca { font-size: 16px; font-weight: 700; color: %primary%; letter-spacing: -0.01em; }
QLineEdit#buscaGlobal {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 6px;
    color: %texto%;
    padding: 6px 12px;
}
QLineEdit#buscaGlobal:hover { border-color: %borda-forte%; }
QLineEdit#buscaGlobal:focus { border: 1px solid %primary%; }
QListWidget#sugestoesBusca {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 8px;
    color: %texto%;
    padding: 4px;
}
QListWidget#sugestoesBusca::item { padding: 4px 8px; border-radius: 6px; }
QListWidget#sugestoesBusca::item:selected { background-color: %primary%; color: %on-primary%; }
QLabel#valorCard { font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: %texto%; }
QLabel#totalPdv { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; color: %texto%; }
/* Números de KPI usam figuras tabulares: a largura de "1" e "8" fica igual e a
   fileira de cartões não "treme" quando o valor é atualizado (ver
   `number-tabular`, quick-reference §6). */
QLabel#valorCard, QLabel[role="metrica"] { font-family: "Inter"; }
QProgressBar {
    border: 1px solid %borda%;
    border-radius: 4px;
    background-color: %surface-muted%;
}
QProgressBar::chunk { background-color: %primary%; border-radius: 4px; }
/* Barra do banner de tolerância (E5, doc §9.3): mesma família âmbar do banner. */
QProgressBar#barraTolerancia { border: 1px solid %atencao-borda%; background-color: %surface%; }
QProgressBar#barraTolerancia::chunk { background-color: %atencao%; }

/* Faturamento: "realizado" é o dado; "previsto" é a projeção. Cor não pode ser
   o único diferenciador (quick-reference §10 `color-guidance`/`pattern-texture`),
   por isso cada série tem rótulo textual e o previsto é mais claro + contornado. */
QProgressBar#barraRealizado::chunk { background-color: %primary%; }
QProgressBar#barraPrevisto {
    background-color: %surface%;
    border: 1px dashed %borda-forte%;
}
QProgressBar#barraPrevisto::chunk { background-color: %primary-container%; }

/* Estado vazio com convite à ação (quick-reference §8 `empty-states`). */
QLabel#vazioCard {
    background: transparent;
    color: %texto-muted%;
    padding: 4px 0;
}
QLabel#legendaSerie { color: %texto-muted%; font-size: 11px; font-weight: 600; }

QWidget#sidebar { background-color: %surface%; border-right: 1px solid %borda%; }
QLabel#grupoMenu {
    color: %texto-muted%;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    /* padding-left 5px + o inset interno do QLabel alinham o rótulo ao texto
       dos itens (QPushButton[nav]) — ver B4. */
    padding: 10px 5px 4px 5px;
}
QPushButton[nav="true"] {
    border: none;
    border-radius: 7px;
    color: %texto-muted%;
    font-weight: 600;
    padding: 7px 10px;
    text-align: left;
}
QPushButton[nav="true"]:hover { background-color: %surface-muted%; color: %texto%; }
QPushButton[nav="true"]:checked { background-color: %primary-container%; color: %primary%; }

QLabel#bannerLeitura {
    background-color: %atencao-container%;
    border: 1px solid %atencao-borda%;
    border-radius: 10px;
    color: %atencao%;
    font-weight: 600;
    padding: 8px 12px;
}

QLabel#bannerErro {
    background-color: %erro-container%;
    border: 1px solid %erro-borda%;
    border-radius: 10px;
    color: %erro%;
    font-weight: 600;
    padding: 8px 12px;
}

QToolButton#menuUsuario {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 999px;
    color: %texto%;
    font-weight: 600;
    padding: 4px 10px;
}
QToolButton#menuUsuario:hover { border-color: %borda-forte%; background-color: %surface-muted%; }
QToolButton#menuUsuario::menu-indicator { image: none; width: 0; }

QPushButton[icone="true"] {
    border: none;
    background: transparent;
    border-radius: 7px;
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
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 12px;
}
QPushButton[chave="true"]:hover { border-color: %borda-forte%; color: %texto%; }
QPushButton[chave="true"]:checked { background-color: %primary%; border-color: %primary%; color: #FFFFFF; }

/* Controle segmentado (visões/filtros) — mesmo visual, por objectName. */
QPushButton#chaveRapida {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
}
QPushButton#chaveRapida:hover { border-color: %borda-forte%; color: %texto%; }
QPushButton#chaveRapida:checked { background-color: %primary%; border-color: %primary%; color: #FFFFFF; }

/* Quadro Kanban (Projetos) — uma coluna por etapa, cartões sem corte. */
QScrollArea#areaQuadro { background: transparent; border: none; }
QFrame#colunaKanban {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 12px;
}
/* Alvo de soltura: tinta de acento — "sugere a direção do gesto" (§8) sem o
   tracejado chamativo do primeiro rascunho. */
QFrame#colunaKanban[alvoDrop="true"] {
    background-color: %primary-container%;
    border: 1px solid %primary%;
}
QLabel#tituloColunaKanban {
    font-size: 11px;
    font-weight: 600;
    color: %texto-muted%;
    letter-spacing: 0.03em;
}
QLabel#contagemKanban {
    background-color: %surface-muted%;
    border: none;
    border-radius: 999px;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 600;
    padding: 1px 8px;
}
QFrame#cartaoKanban {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 10px;
}
QFrame#cartaoKanban:hover { border-color: %borda-forte%; }
QFrame#cartaoKanban:focus { border: 2px solid %primary%; }
QLabel#tituloCartao { font-weight: 600; }

/* Calendário mensal (Agendamento) — grade de 6 semanas, sem rolagem lateral. */
QWidget[role="painelDia"] {
    background-color: %surface%;
    border: 1px solid %borda%;
    border-radius: 10px;
}
QPushButton[navCalendario="true"] { padding: 4px 12px; }
QPushButton[chipEvento="true"] {
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 11px;
    text-align: left;
}
QPushButton[chipEvento="true"][chipTipo="primary"] { background-color: %primary%; color: %on-primary%; }
QPushButton[chipEvento="true"][chipTipo="success"] { background-color: %sucesso-container%; color: %sucesso%; }
QWidget[celulaDia="true"] { background-color: %surface%; border: 1px solid %borda%; border-radius: 8px; }
QWidget[celulaDia="true"][foraDoMes="true"] { background-color: %surface-muted%; }
QWidget[celulaDia="true"]:hover { border-color: %borda-forte%; }
QWidget[celulaDia="true"][selecionada="true"] { border: 2px solid %primary%; }
QWidget[celulaDia="true"][hoje="true"] { border: 2px solid %sucesso%; }

/* Botão de ação compacto dentro de uma linha da grade (ex.: Cancelar). */
QPushButton#acaoLinha {
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 6px;
}

QLabel#secaoForm {
    color: %primary%;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.03em;
    padding-top: 8px;
}

QTableWidget {
    background-color: transparent;
    border: none;
    gridline-color: transparent;
    font-size: 13px;
    selection-background-color: %primary-container%;
    selection-color: %texto%;
}
/* Seleção = tinta de acento na linha inteira; a barra lateral de 3px saiu (§16
   simplicidade: nada de elementos decorativos sem função). */
QTableWidget::item {
    border-bottom: 1px solid %borda%;
    padding: 7px 8px;
}
QTableWidget::item:selected { background-color: %primary-container%; color: %texto%; }
QTableWidget::item:hover { background-color: %surface-muted%; }
QHeaderView::section {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid %borda%;
    color: %texto-muted%;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 8px;
}
QTableCornerButton::section { background-color: transparent; border: none; }

QLabel#vazioTabela {
    background: transparent;
    color: %texto-muted%;
    font-size: 13px;
    padding: 12px;
}

QPushButton#pagBotao {
    border: 1px solid %borda%;
    background-color: %surface%;
    border-radius: 6px;
    color: %texto%;
    font-weight: 600;
    padding: 0;
}
QPushButton#pagBotao:hover { border-color: %borda-forte%; background-color: %surface-muted%; }
QPushButton#pagBotao:disabled { color: %borda-forte%; border-color: %borda%; }

QPushButton[role="ghost"] { border: none; color: %texto-muted%; }
QPushButton[role="ghost"]:hover { color: %erro%; background-color: %erro-container%; }

QWidget#rodape { background-color: %surface%; border-top: 1px solid %borda%; }

/* Banner de aviso em página (ex.: PDV com caixa fechado, M0). */
QWidget#bannerAviso {
    background-color: %atencao-container%;
    border: 1px solid %atencao-borda%;
    border-radius: 8px;
}

/* ============== Tela de Ativação (revisão out/2026) =====================
   Escopo por objectName/property: nada aqui alcança as demais telas.
   Tipografia: título 24/700, rótulo 13/600 (sentence case), auxiliar 12/400. */
QLabel#tituloAtivacao { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
QLabel#tituloSucesso { font-size: 20px; font-weight: 700; }
QLabel#rotuloCampo { font-size: 13px; font-weight: 600; color: %texto%; }
QLabel#ajudaCampo { font-size: 12px; font-weight: 400; color: %texto-muted%; }
QLabel#erroCampo { font-size: 12px; font-weight: 400; color: %erro%; }
QLabel#statusServidor { font-size: 12px; font-weight: 400; }

/* Ações de texto (Sair/Cancelar/Detalhes/Tentar): plano, no azul de ação
   legível sobre o canvas (5,1:1). */
QPushButton#botaoFlat {
    background: transparent;
    border: none;
    color: %acao%;
    font-weight: 600;
    padding: 6px 8px;
}
QPushButton#botaoFlat:hover { color: %acao%; background-color: %surface-muted%; border-radius: 6px; }
QPushButton#botaoFlat:disabled { color: %borda-forte%; }

/* Indicador de progresso (D1): pontos de 8 px, sem cara de botão. */
QLabel[passo="pendente"] { background-color: %borda%; border-radius: 4px; }
QLabel[passo="atual"] { background-color: %primary%; border-radius: 4px; }
QLabel[passo="feito"] { background-color: %sucesso%; border-radius: 4px; }

/* Campos da ativação: borda >= 3:1 (A3), anel de foco de 2 px e estado de
   erro — o padding compensa o pixel extra da borda para não tremer. */
QLineEdit[formAtivacao="true"] { border: 1px solid %borda-campo%; }
QLineEdit[formAtivacao="true"]:hover { border: 1px solid %texto-muted%; }
QLineEdit[formAtivacao="true"]:focus { border: 2px solid %focus%; padding: 7px 9px; }
QLineEdit[formAtivacao="true"][estado="erro"] { border: 2px solid %erro%; padding: 7px 9px; }

/* Barra indeterminada da validação (D2) — só nesta tela. */
QProgressBar#barraAtiva { background-color: %surface-muted%; border: none; border-radius: 2px; }
QProgressBar#barraAtiva::chunk { background-color: %primary%; border-radius: 2px; }
"""


def aplicar_theme(app: QApplication) -> QApplication:
    global FONT_RESOLVIDA
    FONT_RESOLVIDA = _resolver_familia()  # exige QApplication vivo
    fonte = QFont(FONT_RESOLVIDA, 10)
    fonte.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(fonte)
    # Placeholder dos campos no cinza secundário (5,07:1 no branco) — o padrão
    # do tema é mais claro e "aparentava" baixo contraste (revisão PDV nº 8).
    paleta = app.palette()
    paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor(CORES["texto-muted"]))
    app.setPalette(paleta)
    qss = _QSS
    for chave, valor in CORES.items():
        qss = qss.replace(f"%{chave}%", valor)
    qss = qss.replace(f'"{FONT_FAMILY}"', f'"{FONT_RESOLVIDA}"')
    # Ícones dos controles nativos vêm de SVG embutido (ver contra-ícone acima).
    qss = qss.replace("%asset_check%", (_ASSETS / "check.svg").as_posix())
    qss = qss.replace("%asset_ponto%", (_ASSETS / "ponto.svg").as_posix())
    qss = qss.replace("%asset_seta%", (_ASSETS / "seta-combo.svg").as_posix())
    app.setStyleSheet(qss)
    return app
