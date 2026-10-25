"""Configuração comum dos testes do desktop: QApplication offscreen + loop de eventos."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication
from printgest.core import catalogos
from printgest.ui.theme import aplicar_theme


def pytest_sessionstart(session):
    """Patch `rodar` para executar sincronamente ANTES da execução dos testes."""
    print(f"[CONFTEST] pytest_sessionstart called", flush=True)
    import printgest.core.tarefas as tarefas_mod
    import printgest.ui.modulos.agendamento as agendamento_mod
    import printgest.ui.modulos.configuracao as config_mod
    import printgest.ui.modulos.os as os_mod
    import printgest.ui.modulos.financeiro as fin_mod
    import printgest.ui.modulos.fiscal as fiscal_mod
    import printgest.ui.modulos.estoque as est_mod
    import printgest.ui.ativacao as ativacao_mod

    def _rodar_sync(fn, on_ok, on_erro):
        try:
            on_ok(fn())
        except Exception as exc:
            on_erro(str(exc))

    for mod in (tarefas_mod, agendamento_mod, config_mod, os_mod, fin_mod, fiscal_mod, est_mod, ativacao_mod):
        if hasattr(mod, "rodar"):
            mod.rodar = _rodar_sync
            print(f"  [CONFTEST] Patched {mod.__name__}.rodar", flush=True)


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