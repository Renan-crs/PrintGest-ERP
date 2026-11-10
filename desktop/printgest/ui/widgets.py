"""Componentes reutilizáveis das telas 1.x (login, ativação, modo leitura)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QEvent, QRect, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

_ASSETS = Path(__file__).resolve().parent / "assets"

# Marca oficial (out/2026): símbolo "mira" em vetorial. O SVG em assets/ é a
# fonte; o mesmo traço abaixo é o fallback desenhado em código quando o plugin
# de SVG não está disponível.
_MARCA_TRACO = "#0F1B2D"   # navy do símbolo
_MARCA_PONTO = "#1166D6"   # azul do ponto central


def marca_printgest(tamanho: int = 44) -> QLabel:
    """Símbolo oficial do produto (SVG vetorial, fallback desenhada em código).

    Decorativa (A7): `accessibleName` vazio — leitores de tela ignoram.
    """
    caminho = _ASSETS / "printgest-simbolo.svg"
    pm = QIcon(str(caminho)).pixmap(tamanho, tamanho)
    if pm.isNull():  # plugin de SVG ausente: desenha a mira em código
        pm = QPixmap(tamanho, tamanho)
        escala = tamanho / 64.0
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(escala, escala)
        caneta = QPen(QColor(_MARCA_TRACO), 4)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(caneta)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(17, 17, 30, 30)  # círculo (centro 32,32 r15)
        for linha in (QRectF(30, 4, 4, 18), QRectF(30, 42, 4, 18),
                      QRectF(4, 30, 18, 4), QRectF(42, 30, 18, 4)):
            p.drawRoundedRect(linha, 2, 2)  # retículas com pontas arredondadas
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_MARCA_PONTO))
        p.drawEllipse(28, 28, 8, 8)  # ponto central
        p.end()
    lbl = QLabel()
    lbl.setPixmap(pm)
    lbl.setFixedSize(tamanho, tamanho)
    lbl.setAccessibleName("")
    return lbl


def icone_printgest() -> QIcon:
    """Ícone das janelas (quadrado azul): taskbar/barra de título."""
    return QIcon(str(_ASSETS / "printgest-icone.svg"))


def aplicar_estilo(widget: QWidget) -> None:
    """Recompila o QSS de `widget` após mudanças de propriedade dinâmica."""
    estilo = widget.style()
    estilo.unpolish(widget)
    estilo.polish(widget)


# =============================================================================
# Helpers para estados visuais (refatoração de repetição de setProperty)
# =============================================================================

def aplicar_estado(widget: QWidget, tipo: str) -> None:
    """Aplica propriedade de estado e recompila o estilo.
    
    Tipos comuns: 'success', 'error', 'atencao', 'muted', 'primary', 
                  'secondary', 'danger', 'ghost', 'subtitulo', 'painelDia'
    
    Uso: aplicar_estado(self._lbl_estoque, 'atencao')
    """
    widget.setProperty("role", tipo)
    aplicar_estilo(widget)


def estado_sucesso(widget: QWidget) -> None:
    """Estado verde/sucesso."""
    aplicar_estado(widget, "success")


def estado_erro(widget: QWidget) -> None:
    """Estado vermelho/erro."""
    aplicar_estado(widget, "error")


def estado_atencao(widget: QWidget) -> None:
    """Estado amarelo/atencao."""
    aplicar_estado(widget, "atencao")


def estado_muted(widget: QWidget) -> None:
    """Estado cinza/desativado/talvez."""
    aplicar_estado(widget, "muted")


def estado_danger(widget: QWidget) -> None:
    """Estado perigo/danger."""
    aplicar_estado(widget, "danger")


def estado_ghost(widget: QWidget) -> None:
    """Estado ghost (botao secundario/transparente)."""
    aplicar_estado(widget, "ghost")


def estado_subtitulo(widget: QWidget) -> None:
    """Estado subtitle/label secundario."""
    aplicar_estado(widget, "subtitulo")


def estado_secundario(widget: QWidget) -> None:
    """Estado secundario (botao/eticheta não primaria)."""
    aplicar_estado(widget, "secondary")


def estado_primario(widget: QWidget) -> None:
    """Estado primario (botao/eticheta principal)."""
    aplicar_estado(widget, "primary")


def botao_com_atalho(
    texto: str, atalho: str = "", role: str = ""
) -> tuple[QWidget, QPushButton]:
    """Botão com hint de teclado ao lado (padrão dos mockups Fluent)."""
    caixa = QWidget()
    caixa.setObjectName("botaoKbd")
    layout = QHBoxLayout(caixa)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(6)

    botao = QPushButton(texto)
    if role:
        botao.setProperty("role", role)

    if atalho:
        chave = QLabel(atalho)
        chave.setProperty("kbdHint", "true")
        chave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chave.setFixedHeight(18)
        layout.addWidget(botao, 1)
        layout.addWidget(chave, 0, Qt.AlignmentFlag.AlignRight)
    else:
        layout.addWidget(botao)
    return caixa, botao


def badge(texto: str, estilo: str = "") -> QLabel:
    """Pílula de status estilo mockup (ex.: Tolerância Offline: 72 Horas)."""
    lbl = QLabel(texto)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setProperty("badge", "true")
    if estilo:
        lbl.setProperty("badgeStyle", estilo)
    return lbl


def formatar_datahora(valor: object) -> str:
    """ISO-8601 (com ou sem fuso) do daemon → `dd/mm/aaaa hh:mm` (vazia se nulo)."""
    if not valor:
        return ""
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    return momento.strftime("%d/%m/%Y %H:%M")


class EtiquetaQuebra(QLabel):
    """QLabel com quebra que nunca é comprimida abaixo do texto (A2).

    O `heightForWidth` do QLabel é ignorado por alguns arranjos de layout —
    o resultado é texto cortado na vertical. Aqui o `minimumHeight` vira o
    piso real da altura necessária, recalculado a cada redimensionamento.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setWordWrap(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(evento)
        largura = max(self.width(), 1)
        necessaria = self.heightForWidth(largura)
        if necessaria <= 0:
            necessaria = self.sizeHint().height()
        self.setMinimumHeight(max(necessaria, self.sizeHint().height()))


class ElideLabel(QLabel):
    """`QLabel` de uma linha que elide o texto quando não couber.

    O texto completo permanece acessível por `text()` e vira tooltip — o
    desenho (paintEvent) é que encurta visualmente. Assim nenhum rótulo do
    dashboard é cortado sem uma forma de ler o valor inteiro.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        # Não impõe a largura do texto: o rótulo pode encolher (elide) para
        # liberar espaço em telas estreitas, sem travar o layout.
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        painter = QPainter(self)
        metrics = self.fontMetrics()
        elidido = metrics.elidedText(
            self.text(), Qt.TextElideMode.ElideRight, max(0, self.width())
        )
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.rect(), int(self.alignment()), elidido)

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(evento)
        self._atualizar_tooltip()

    def _atualizar_tooltip(self) -> None:
        completo = self.text()
        cabe = self.fontMetrics().horizontalAdvance(completo) <= max(0, self.width())
        self.setToolTip("" if cabe else completo)


class FlowLayout(QLayout):
    """Layout que dispõe os itens em linhas e reflui quando a largura muda.

    Usado no grid de KPIs do Início: em janelas estreitas os cartões descem de
    linha em vez de serem espremidos (evita truncamento).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        margem: int = 0,
        espaco_h: int = 12,
        espaco_v: int = 12,
    ) -> None:
        super().__init__(parent)
        self._itens: list = []
        self._espaco_h = espaco_h
        self._espaco_v = espaco_v
        self.setContentsMargins(margem, margem, margem, margem)

    def addItem(self, item) -> None:  # noqa: N802 (API Qt)
        self._itens.append(item)

    def count(self) -> int:
        return len(self._itens)

    def itemAt(self, indice: int):  # noqa: N802 (API Qt)
        if 0 <= indice < len(self._itens):
            return self._itens[indice]
        return None

    def takeAt(self, indice: int):  # noqa: N802 (API Qt)
        if 0 <= indice < len(self._itens):
            return self._itens.pop(indice)
        return None

    def expandingDirections(self):  # noqa: N802 (API Qt)
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (API Qt)
        return True

    def heightForWidth(self, largura: int) -> int:  # noqa: N802 (API Qt)
        return self._dispor(QRect(0, 0, largura, 0), aplicar=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (API Qt)
        super().setGeometry(rect)
        self._dispor(rect, aplicar=True)

    def sizeHint(self) -> QSize:  # noqa: N802 (API Qt)
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 (API Qt)
        tamanho = QSize()
        for item in self._itens:
            tamanho = tamanho.expandedTo(item.minimumSize())
        margens = self.contentsMargins()
        tamanho += QSize(
            margens.left() + margens.right(), margens.top() + margens.bottom()
        )
        return tamanho

    def _dispor(self, rect: QRect, aplicar: bool) -> int:
        margens = self.contentsMargins()
        x = rect.x() + margens.left()
        y = rect.y() + margens.top()
        limite = rect.right() - margens.right()
        altura_linha = 0
        for item in self._itens:
            hint = item.sizeHint()
            if altura_linha and x + hint.width() > limite:
                x = rect.x() + margens.left()
                y += altura_linha + self._espaco_v
                altura_linha = 0
            if aplicar:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._espaco_h
            altura_linha = max(altura_linha, hint.height())
        return y + altura_linha + margens.bottom() - rect.y()


# =============================================================================
# Skeleton de carregamento
# =============================================================================
# Barras cinza-claras com brilho deslizante, pintadas sobre o contêiner (card
# ou viewport da tabela) enquanto os dados chegam do banco/daemon. O fundo é
# transparente: o skeleton não esconde a estrutura, ele a ANTICIPA. Com a
# preferência "reduzir animações" do Windows, as barras ficam estáticas.

_COR_BARRA = "#E9E9EE"
_COR_BRILHO = QColor(255, 255, 255, 160)


def animacoes_habilitadas() -> bool:
    """Mesma preferência do Windows respeitada pela tela de ativação (D7)."""
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        ligado = wintypes.BOOL()
        ok = ctypes.windll.user32.SystemParametersInfoW(
            0x1042, 0, ctypes.byref(ligado), 0  # SPI_GETCLIENTAREAANIMATION
        )
        return bool(ok and ligado.value)
    except Exception:  # noqa: BLE001 — fora do Windows ou indisponível: liga
        return True


class SkeletonBase(QWidget):
    """Blocos de carregamento com brilho animado, sobre um widget-pai.

    A geometria acompanha o pai (event filter de resize) e `mostrar()`/
    `ocultar()` controlam a exibição. Subclasses definem as barras em
    `_especificar()` como retângulos absolutos `(x, y, w, h)`.
    """

    def __init__(self, pai: QWidget) -> None:
        super().__init__(pai)
        self._pai = pai
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pai.installEventFilter(self)
        self._fase = 0.0
        self._animacao = QVariantAnimation(self)
        self._animacao.setStartValue(0.0)
        self._animacao.setEndValue(1.0)
        self._animacao.setDuration(1400)
        self._animacao.setLoopCount(-1)
        self._animacao.valueChanged.connect(self._fase_mudou)
        if animacoes_habilitadas():
            self._animacao.start()

    # ------------------------------------------------------------- controle

    def eventFilter(self, obj, evento):  # noqa: N802 (API Qt)
        if obj is self._pai and evento.type() == QEvent.Type.Resize:
            self.setGeometry(self._pai.rect())
        return False

    def mostrar(self) -> None:
        self.setGeometry(self._pai.rect())
        self.show()
        self.raise_()

    def ocultar(self) -> None:
        self.hide()

    # -------------------------------------------------------------- pintura

    def _especificar(self) -> list[tuple[float, float, float, float]]:
        """Retângulos das barras em pixels absolutos (x, y, w, h)."""
        raise NotImplementedError

    def _fase_mudou(self, valor) -> None:
        self._fase = float(valor)
        self.update()

    def paintEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pintor.setPen(Qt.PenStyle.NoPen)
        barras = self._especificar()
        pintor.setBrush(QColor(_COR_BARRA))
        caminho = QPainterPath()
        for x, y, largura, altura in barras:
            rect = QRectF(x, y, max(largura, 4), altura)
            caminho.addRoundedRect(rect, 3, 3)
            pintor.drawRoundedRect(rect, 3, 3)
        # Brilho: faixa vertical que varre o widget, clipada às barras — o
        # movimento fica no material, sem lavar o contêiner atrás.
        if self._animacao.state() == QVariantAnimation.State.Running:
            base = max(self.width() - 1, 1)
            largura_brilho = max(base * 0.35, 60)
            posicao = self._fase * (base + largura_brilho) - largura_brilho
            gradiente = QLinearGradient(posicao, 0, posicao + largura_brilho, 0)
            gradiente.setColorAt(0.0, QColor(255, 255, 255, 0))
            gradiente.setColorAt(0.5, _COR_BRILHO)
            gradiente.setColorAt(1.0, QColor(255, 255, 255, 0))
            pintor.save()
            pintor.setClipPath(caminho)
            pintor.fillRect(self.rect(), gradiente)
            pintor.restore()


class SkeletonTabela(SkeletonBase):
    """Linhas de skeleton sobre uma tabela/lista (padrão das listagens)."""

    _ALTURA_LINHA = 30
    _ALTURA_BARRA = 14

    def __init__(self, pai: QWidget, linhas: int | None = None) -> None:
        self._linhas_fixas = linhas
        super().__init__(pai)

    def _especificar(self) -> list[tuple[float, float, float, float]]:
        total = self.height()
        if self._linhas_fixas is not None:
            quantidade = self._linhas_fixas
        else:
            quantidade = max(1, total // (self._ALTURA_LINHA + 2))
        barras: list[tuple[float, float, float, float]] = []
        for indice in range(quantidade):
            y = 4 + indice * (self._ALTURA_LINHA + 2)
            if y + self._ALTURA_BARRA > total:
                break
            largura = self.width()
            # Imita o desenho da listagem: nº pequeno, descrição longa,
            # duas colunas medianas — mesma leitura da tabela real.
            barras.extend(
                [
                    (largura * 0.03, y, largura * 0.06, self._ALTURA_BARRA),
                    (largura * 0.12, y, largura * 0.40, self._ALTURA_BARRA),
                    (largura * 0.55, y, largura * 0.14, self._ALTURA_BARRA),
                    (largura * 0.72, y, largura * 0.12, self._ALTURA_BARRA),
                ]
            )
        return barras


class SkeletonCartao(SkeletonBase):
    """Skeleton de card de dado (título, valor e subtexto) do dashboard."""

    def _especificar(self) -> list[tuple[float, float, float, float]]:
        margem_x, margem_y = 14, 12
        largura = max(self.width() - margem_x * 2, 40)
        topo = margem_y
        return [
            (margem_x, topo, largura * 0.40, 10),            # título
            (margem_x, topo + 18, largura * 0.70, 20),       # valor
            (margem_x, topo + 46, largura * 0.52, 10),       # subtexto
        ]