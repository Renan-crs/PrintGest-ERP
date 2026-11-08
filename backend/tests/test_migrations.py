"""Migrations no startup: caminho congelado (exe) e caminho dev (subprocesso)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.core import migrations
from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Mesmo critério do conftest: no CI a URL vem de DATABASE_URL (serviço
# efêmero do workflow); local usa o Postgres portable da .dev.
_URL = os.environ.get("DATABASE_URL", "").strip()
if not _URL.startswith("postgresql"):
    _URL = "postgresql://printgest:printgest@127.0.0.1:5432/printgest_test"
TESTE_URL = _URL.replace("postgresql://", "postgresql+psycopg://", 1)


def test_migrations_congeladas_pela_api_python(monkeypatch):
    """Exe congelado não tem `python -m` — a atualização roda in-process.

    `_MEIPASS` aponta para o backend real: `alembic/` está lá e o banco de
    teste já está no `head` (a suíte migrou) — a chamada é idempotente.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(BACKEND_DIR), raising=False)
    monkeypatch.setattr(settings, "auto_migrate", True)
    monkeypatch.setattr(settings, "database_url", TESTE_URL)

    migrations.aplicar_migrations()  # não deve explodir nem recriar nada


def test_migrations_dev_continua_usando_subprocesso(monkeypatch):
    """Sem congelamento o fluxo histórico é preservado (subprocesso alembic)."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    capturado: dict = {}

    def run_fake(comando, **kwargs):
        capturado["comando"] = comando
        capturado["cwd"] = kwargs.get("cwd")

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(migrations.subprocess, "run", run_fake)
    monkeypatch.setattr(settings, "auto_migrate", True)
    monkeypatch.setattr(settings, "database_url", TESTE_URL)

    migrations.aplicar_migrations()

    assert capturado["comando"][1:] == ["-m", "alembic", "upgrade", "head"]
    assert capturado["cwd"] == str(BACKEND_DIR)


def test_migrations_desligadas_nao_fazem_nada(monkeypatch):
    monkeypatch.setattr(settings, "auto_migrate", False)
    chamado = {"v": False}

    def run_fake(*_a, **_k):
        chamado["v"] = True
        raise AssertionError("não deveria rodar nada")

    monkeypatch.setattr(migrations.subprocess, "run", run_fake)
    migrations.aplicar_migrations()
    assert chamado["v"] is False
