"""Testes do módulo de animação (§4/§5) — foco no bug relatado em campo.

O offscreen desliga animações por padrão (`animacoes_habilitadas`), então a
suíte nunca exercitava `animar_largura`; o crash só aparecia no GUI real:

    RuntimeError: Internal C++ object (QVariantAnimation) already deleted

`DeleteWhenStopped` apaga o objeto C++ ao fim, mas o wrapper Python continuava
guardado em `widget._anim_largura` — o colapso seguinte do menu lateral morria.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractAnimation
from PySide6.QtWidgets import QWidget

import printgest.ui.animacao as animacao


def _habilitar_animacoes(monkeypatch):
    monkeypatch.setattr(animacao, "animacoes_habilitadas", lambda: True)
    return animacao


def test_wrapper_morto_no_slot_nao_derruba_o_proximo_colapso(app, monkeypatch):
    """Regressão exata do relato: wrapper morto esquecido + nova chamada."""
    animacao_ = _habilitar_animacoes(monkeypatch)
    w = QWidget()

    primeira = animacao_.animar_largura(w, 100, 200)
    assert primeira is not None
    primeira.stop()  # DeleteWhenStopped: o C++ já era; wrapper sobra no slot
    app.processEvents()
    w._anim_largura = primeira  # simula o esquecimento que causava o crash

    segunda = animacao_.animar_largura(w, 200, 100)  # antes: RuntimeError
    assert segunda is not None
    segunda.stop()


def test_slot_limpa_na_conclusao_natural(app, monkeypatch):
    """Terminando, o slot `_anim_largura` é limpo (caso comum do menu lateral).

    A conclusão é forçada de forma síncrona com `setCurrentTime(duration)`:
    deixar a animação correr com ticks REAIS dentro do `pumpar` (processEvents
    sem event loop) corrompia o timer de animação do Qt no offscreen e derrubava
    a suíte com abort — o comportamento natural só é exercitado no GUI real.
    """
    animacao_ = _habilitar_animacoes(monkeypatch)
    w = QWidget()

    a = animacao_.animar_largura(w, 100, 200)
    assert getattr(w, "_anim_largura", None) is a

    a.setCurrentTime(a.duration())  # salta para o fim: finished + limpeza
    app.processEvents()  # entrega o deleteLater
    assert getattr(w, "_anim_largura", None) is None
    assert w.width() == 200


def test_nova_animacao_interrompe_a_anterior(app, monkeypatch):
    """Colapsar no meio de uma animação reverte sem salto nem crash (§3)."""
    animacao_ = _habilitar_animacoes(monkeypatch)
    w = QWidget()
    w.setFixedWidth(100)

    indo = animacao_.animar_largura(w, 100, 300)
    voltando = animacao_.animar_largura(w, w.width(), 100)

    assert indo.state() != QAbstractAnimation.State.Running
    assert voltando.state() == QAbstractAnimation.State.Running
    voltando.stop()


def test_sem_animacoes_aplica_estado_final(app):
    """Offscreen (padrão da suíte): aplica direto e chama o ao_fim."""
    chamado = []
    w = QWidget()
    animacao.animar_largura(w, 100, 64, ao_fim=lambda: chamado.append(True))
    assert w.width() == 64
    assert chamado == [True]
