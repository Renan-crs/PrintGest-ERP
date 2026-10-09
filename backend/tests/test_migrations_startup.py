"""Startup: aplicação de migrations Alembic (evita drift de schema).

O helper é exercitado com `subprocess.run` mockado — nenhum banco é tocado.
"""

from types import SimpleNamespace

import pytest

from app.core import migrations


def _fake_run_factory(chamadas, returncode=0, stdout="", stderr=""):
    def _fake_run(cmd, **kwargs):
        chamadas.append((cmd, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return _fake_run


def test_desabilitado_nao_executa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(migrations.subprocess, "run", _fake_run_factory(chamadas))
    monkeypatch.setattr(migrations.settings, "auto_migrate", False)

    migrations.aplicar_migrations()

    assert chamadas == []


def test_habilitado_roda_upgrade_head(monkeypatch):
    chamadas = []
    monkeypatch.setattr(migrations.subprocess, "run", _fake_run_factory(chamadas))
    monkeypatch.setattr(migrations.settings, "auto_migrate", True)

    migrations.aplicar_migrations()

    assert len(chamadas) == 1
    cmd, kwargs = chamadas[0]
    assert cmd[1:] == ["-m", "alembic", "upgrade", "head"]
    assert kwargs["env"]["PRINTGEST_DATABASE_URL"] == migrations.settings.database_url
    assert kwargs["capture_output"] is True


def test_falha_aborta_startup(monkeypatch):
    monkeypatch.setattr(
        migrations.subprocess,
        "run",
        _fake_run_factory([], returncode=1, stdout="saida", stderr="falhou"),
    )
    monkeypatch.setattr(migrations.settings, "auto_migrate", True)

    with pytest.raises(RuntimeError) as exc:
        migrations.aplicar_migrations()

    assert "alembic upgrade head" in str(exc.value)
    assert "falhou" in str(exc.value)
