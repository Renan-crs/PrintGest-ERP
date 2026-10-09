"""Configuração comum dos testes do desktop: QApplication offscreen + loop de eventos."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication
from printgest.core import catalogos
from printgest.ui.theme import aplicar_theme


@pytest.fixture(scope="session")
def app():
    aplicativo = QApplication.instance() or QApplication([])
    aplicar_theme(aplicativo)
    yield aplicativo


@pytest.fixture(autouse=True)
def _catalogos_isolados():
    """Zera o cache de catálogos antes/depois de cada teste (estado de módulo)."""
    catalogos.limpar()
    yield
    catalogos.limpar()


@pytest.fixture
def pumpar(app):
    def _pump_ate(condicao, timeout_ms=4000):
        timer = QElapsedTimer()
        timer.start()
        while not condicao():
            app.processEvents()
            if timer.elapsed() > timeout_ms:
                pytest.fail("o loop de eventos não atingiu a condição a tempo")

    return _pump_ate