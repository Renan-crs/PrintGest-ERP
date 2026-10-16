"""Movimento fluido estilo Apple, traduzido para Qt/PySide6.

Baseado em *Designing Fluid Interfaces* (WWDC 2018) e nos demais princípios do
`apple-design`. O que faz uma interface "viva" aqui:

- **Resposta (§1):** durações curtíssimas (0.2–0.3 s) — nada atrasa o input.
- **Comportamento > animação (§4):** *springs* viram curvas de easing; o padrão
  é criticamente amortecido (``OutCubic``, sem overshoot). ``OutBack`` só para
  gestos que carregam momento (um cartão arremessado).
- **Interrompibilidade (§3):** toda animação parte do valor **atual** em tela,
  nunca do alvo — dá para pegar no meio e reverter sem "salto".
- **Materializar (§12):** superfícies flutuantes (diálogos) surgem com fade, não
  aparecem secas.
- **Reduced motion (§14):** quando o sistema pede menos movimento — ou quando
  não há tela real (plataforma ``offscreen``, usada nos testes) — nada anima e o
  estado final é aplicado de imediato.

Uso: sempre guarde o retorno (a referência mantém a animação viva) ou use
``guardar`` para anexá-la ao widget.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

# ----------------------------------------------------------------- parâmetros
# Apple: response do drawer/sheet ~0.3 s; reposicionamento ~0.4 s. Em desktop
# (mouse/teclado) encurtamos para parecer instantâneo sem perder a continuidade.
RESPOSTA_CURTA = 180   # micro-transições (fade de página, materializar)
RESPOSTA_MEDIA = 260   # colapso de barra lateral, crescimento/reposição


def _curva(tipo: QEasingCurve.Type, overshoot: float | None = None) -> QEasingCurve:
    curva = QEasingCurve(tipo)
    if overshoot is not None:
        curva.setOvershoot(overshoot)
    return curva


# Criticamente amortecido: chega e para, sem quicar. É o "house style" (§4).
CURVA_PADRAO = _curva(QEasingCurve.Type.OutCubic)
# Momento: leve overshoot — só quando um gesto (flick/arraste) precede (§4/§6).
CURVA_MOMENTO = _curva(QEasingCurve.Type.OutBack, overshoot=1.1)
# Movimento pequeno e seco (nav, ícones): quinta potência = bem snappy.
CURVA_RAPIDA = _curva(QEasingCurve.Type.OutQuint)


def animacoes_habilitadas() -> bool:
    """Se o movimento deve acontecer (§14).

    Desliga quando o SO pede menos movimento e quando rodamos sem tela real
    (``offscreen``) — o que mantém os testes determinísticos.
    """
    app = QApplication.instance()
    if app is None:
        return False
    if QGuiApplication.platformName() == "offscreen":
        return False
    try:
        return bool(QGuiApplication.styleHints().animationsEnabled)
    except AttributeError:  # Qt antigo: assume ligado
        return True


def guardar(widget: QWidget, animacao: QAbstractAnimation) -> QAbstractAnimation:
    """Anexa a animação ao widget (evita o coletor de lixo interromper)."""
    atuais = getattr(widget, "_animacoes_ativas", None)
    if atuais is None:
        atuais = []
        widget._animacoes_ativas = atuais
    atuais.append(animacao)
    animacao.finished.connect(lambda: atuais.remove(animacao) if animacao in atuais else None)
    return animacao


# --------------------------------------------------------------- propriedades
def suavizar(
    widget: QWidget,
    propriedade: bytes,
    de,
    para,
    duracao: int = RESPOSTA_MEDIA,
    curva: QEasingCurve | None = None,
) -> QPropertyAnimation | None:
    """Anima uma propriedade Qt (``windowOpacity``, ``pos``, ``maximumWidth``…)."""
    if not animacoes_habilitadas():
        try:
            widget.setProperty(propriedade.decode(), para)
        except Exception:  # propriedade sem setter Qt: ignora
            pass
        return None
    anim = QPropertyAnimation(widget, propriedade, widget)
    anim.setStartValue(de)
    anim.setEndValue(para)
    anim.setDuration(duracao)
    anim.setEasingCurve(curva or CURVA_PADRAO)
    guardar(widget, anim)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


# ------------------------------------------------------------- largura (painel)
def animar_largura(
    widget: QWidget,
    de: int,
    para: int,
    duracao: int = RESPOSTA_MEDIA,
    ao_fim: Callable[[], None] | None = None,
) -> QVariantAnimation | None:
    """Colapsa/expande um painel animando a largura fixa (§4, §5).

    ``QWidget`` não expõe a largura como propriedade animável, então usamos uma
    ``QVariantAnimation`` que fixa ``minimum``/``maximum`` a cada passo — o layout
    continua refluindo junto (nada de "salto").
    """
    anterior = getattr(widget, "_anim_largura", None)
    if anterior is not None and anterior.state() == QAbstractAnimation.State.Running:
        anterior.stop()

    if not animacoes_habilitadas():
        widget.setFixedWidth(para)
        if ao_fim:
            ao_fim()
        return None

    anim = QVariantAnimation(widget)
    anim.setStartValue(int(de))
    anim.setEndValue(int(para))
    anim.setDuration(duracao)
    anim.setEasingCurve(CURVA_PADRAO)

    def _passo(valor) -> None:
        widget.setFixedWidth(int(valor))

    anim.valueChanged.connect(_passo)
    if ao_fim:
        anim.finished.connect(lambda: ao_fim())
    widget._anim_largura = anim
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


# ----------------------------------------------------------------- materializar
def aparecer(
    widget: QWidget,
    duracao: int = RESPOSTA_CURTA,
    ao_fim: Callable[[], None] | None = None,
) -> QPropertyAnimation | None:
    """Faz o widget "materializar" com fade a partir do valor atual (§3, §12).

    Ao terminar, o efeito de opacidade é removido para o widget voltar ao caminho
    de pintura normal (não vale a pena manter uma camada offscreen para sempre).
    """
    if not animacoes_habilitadas() or widget is None:
        if ao_fim:
            ao_fim()
        return None

    efeito = widget.graphicsEffect()
    if efeito is not None and not isinstance(efeito, QGraphicsOpacityEffect):
        # Já há outro efeito (ex.: sombra): não sobrepor — entrega direto.
        if ao_fim:
            ao_fim()
        return None
    if efeito is None:
        efeito = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(efeito)

    efeito.setOpacity(max(0.0, float(efeito.opacity())))
    anim = QPropertyAnimation(efeito, b"opacity", widget)
    anim.setStartValue(max(0.0, float(efeito.opacity())))
    anim.setEndValue(1.0)
    anim.setDuration(duracao)
    anim.setEasingCurve(CURVA_PADRAO)

    def _fim() -> None:
        # Remove a camada no próximo tick (fora do callback da própria animação).
        QTimer.singleShot(0, lambda: widget.setGraphicsEffect(None))
        if ao_fim:
            ao_fim()

    anim.finished.connect(_fim)
    guardar(widget, anim)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


def revelar_janela(janela: QWidget, duracao: int = RESPOSTA_CURTA) -> None:
    """Superfície flutuante (diálogo) surge com fade, como um material (§12)."""
    if not animacoes_habilitadas():
        return
    try:
        janela.setWindowOpacity(0.0)
    except Exception:
        return
    anim = QPropertyAnimation(janela, b"windowOpacity", janela)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(duracao)
    anim.setEasingCurve(CURVA_PADRAO)
    guardar(janela, anim)
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


# --------------------------------------------------------------- pixmap de arraste
def pixmap_com_sombra(widget: QWidget, elevacao: int = 18, dy: int = 6):
    """Renderiza ``widget`` como pixmap flutuante (com sombra) para o ``QDrag``.

    Dá a sensação de o cartão "levantar" da superfície ao ser pego (§12: peso da
    material; §8: sugerir a direção do gesto). Retorna ``None`` sem movimento.
    """
    if not animacoes_habilitadas():
        return None
    try:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QGraphicsDropShadowEffect

        sombra = QGraphicsDropShadowEffect(widget)
        sombra.setBlurRadius(elevacao)
        sombra.setOffset(0, dy)
        sombra.setColor(QColor(0, 0, 0, 70))
        anterior = widget.graphicsEffect()
        widget.setGraphicsEffect(sombra)
        pixmap = widget.grab()
        widget.setGraphicsEffect(anterior)
        return pixmap
    except Exception:
        return None


__all__ = [
    "RESPOSTA_CURTA",
    "RESPOSTA_MEDIA",
    "CURVA_PADRAO",
    "CURVA_MOMENTO",
    "CURVA_RAPIDA",
    "animacoes_habilitadas",
    "guardar",
    "suavizar",
    "animar_largura",
    "aparecer",
    "revelar_janela",
    "pixmap_com_sombra",
    "QPoint",
]
