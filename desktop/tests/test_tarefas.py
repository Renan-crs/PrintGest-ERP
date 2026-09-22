"""Testes do despachante de tarefas em background (`printgest.core.tarefas`).

Valida que o resultado chega de volta na thread principal via loop de eventos.
"""

from __future__ import annotations

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from printgest.core.tarefas import rodar

MODELO_URL = "http://daemon.test"


@pytest.fixture(scope="session")
def app():
    aplicativo = QApplication.instance() or QApplication([])
    yield aplicativo


def _pump_ate(app, condicao, timeout_ms=4000):
    from PySide6.QtCore import QElapsedTimer

    timer = QElapsedTimer()
    timer.start()
    while not condicao():
        app.processEvents()
        if timer.elapsed() > timeout_ms:
            pytest.fail("a tarefa em background não entregou o resultado a tempo")


def test_resultado_entregue_no_main_thread(app):
    entrega: list = []

    def chamar():
        return 7 * 6

    def ok(valor):
        entrega.append(("ok", valor, threading.current_thread().name))

    def erro(msg):
        entrega.append(("erro", msg))

    rodar(chamar, ok, erro)
    _pump_ate(app, lambda: entrega)

    assert entrega[0][0] == "ok"
    assert entrega[0][1] == 42
    assert entrega[0][2] == threading.main_thread().name


def test_erro_entregue_na_thread_principal(app):
    entrega: list = []

    def chamar():
        raise RuntimeError("falha simulada")

    def ok(_):
        entrega.append(("ok",))

    def erro(msg):
        entrega.append(("erro", msg))

    rodar(chamar, ok, erro)
    _pump_ate(app, lambda: entrega)

    assert entrega[0][0] == "erro"
    assert "falha simulada" in entrega[0][1]


def test_callbacks_sem_tremer_o_usuario(app):
    """Callbacks que ignoram o valor (`on_ok()`) não podem quebrar a entrega."""
    entrega: list = []

    def chamar():
        return True

    def ok(_):
        entrega.append("ok")

    rodar(chamar, ok, lambda _: entrega.append("erro"))
    _pump_ate(app, lambda: entrega)
    assert entrega == ["ok"]