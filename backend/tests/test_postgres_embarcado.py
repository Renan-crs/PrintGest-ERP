"""Testes do PostgreSQL embarcado (preparação do cluster na instalação)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import postgres_embarcado as pg
from app.core.config import settings

TESTE_URL = "postgresql+psycopg://printgest:printgest@127.0.0.1:5433/printgest"


class _Resultado:
    def __init__(self, rc=0, saida="", erro=""):
        self.returncode = rc
        self.stdout = saida
        self.stderr = erro


def _instalar_binarios(raiz: Path) -> Path:
    bin_dir = raiz / "pgsql" / "bin"
    bin_dir.mkdir(parents=True)
    for nome in ("initdb.exe", "pg_ctl.exe", "pg_isready.exe", "psql.exe"):
        (bin_dir / nome).write_text("")
    return bin_dir


def test_partes_url_lê_host_porta_usuario_banco(monkeypatch):
    monkeypatch.setattr(settings, "database_url", TESTE_URL)
    assert pg._partes_url() == ("127.0.0.1", 5433, "printgest", "printgest")


def test_partes_url_porta_padrao_5432(monkeypatch):
    monkeypatch.setattr(
        settings, "database_url", "postgresql+psycopg://u:p@127.0.0.1/dba"
    )
    assert pg._partes_url() == ("127.0.0.1", 5432, "u", "dba")


def test_partes_url_rejeita_host_remoto(monkeypatch):
    monkeypatch.setattr(
        settings, "database_url", "postgresql+psycopg://u:p@servidor.com/db"
    )
    with pytest.raises(RuntimeError, match="127.0.0.1"):
        pg._partes_url()


def test_partes_url_rejeita_esquema_estranho(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite:///arquivo.db")
    with pytest.raises(RuntimeError, match="inesperado"):
        pg._partes_url()


def test_raiz_por_configuracao_vence_o_padrao(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "pg_raiz", str(tmp_path))
    assert pg.raiz_do_postgres() == tmp_path


def test_raiz_congelada_e_irma_da_pasta_do_exe(monkeypatch, tmp_path):
    """Layout do instalador: {app}\\PrintGestAPI\\PrintGestAPI.exe + {app}\\postgres.

    A raiz é a pasta IRMÃ da pasta do executável — `parent` em vez de
    `parent.parent` apontaria para {app}\\PrintGestAPI\\postgres (bug cobrado
    no smoke test da instalação).
    """
    import sys

    api_dir = tmp_path / "PrintGestAPI"
    api_dir.mkdir(parents=True)

    monkeypatch.setattr(settings, "pg_raiz", "")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(api_dir / "PrintGestAPI.exe"))

    assert pg.raiz_do_postgres() == tmp_path / "postgres"


def test_raiz_padrao_do_repositorio_aponta_para_dev(monkeypatch):
    monkeypatch.setattr(settings, "pg_raiz", "")
    esperado = Path(pg.__file__).resolve().parents[3] / ".dev" / "postgres"
    assert pg.raiz_do_postgres() == esperado


def test_garantir_postgres_primeira_execucao(tmp_path, monkeypatch):
    """initdb → pg_ctl start → pg_isready → CREATE DATABASE do banco da URL."""
    raiz = tmp_path / "postgres"
    _instalar_binarios(raiz)
    data_dir = raiz / "data"
    log = raiz / "postgres.log"

    monkeypatch.setattr(settings, "database_url", TESTE_URL)
    monkeypatch.setattr(settings, "pg_raiz", str(raiz))

    chamadas: list[list[str]] = []

    def run_fake(comando, **_):
        chamadas.append([Path(c).name for c in comando])
        ferramenta = Path(comando[0]).name
        if ferramenta == "initdb.exe":
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / "PG_VERSION").write_text("16")
            return _Resultado(rc=0)
        if ferramenta == "pg_ctl.exe" and comando[1] == "status":
            return _Resultado(rc=1)  # parado
        if ferramenta == "pg_ctl.exe" and comando[1] == "start":
            (data_dir / "postmaster.pid").write_text("no-ar")
            return _Resultado(rc=0)
        if ferramenta == "pg_isready.exe":
            return _Resultado(rc=0 if (data_dir / "postmaster.pid").exists() else 1)
        if ferramenta == "psql.exe":
            if "CREATE DATABASE" in " ".join(comando):
                return _Resultado(rc=0)
            return _Resultado(rc=0, saida="\n")  # banco ainda não existe
        raise AssertionError(f"ferramenta inesperada: {ferramenta}")

    monkeypatch.setattr(pg.subprocess, "run", run_fake)

    pg.garantir_postgres()

    nomes = [c[0] for c in chamadas]
    # initdb → status (parado) → start → isready → existência do banco → CREATE
    assert nomes == [
        "initdb.exe",
        "pg_ctl.exe",
        "pg_ctl.exe",
        "pg_isready.exe",
        "psql.exe",
        "psql.exe",
    ]
    # O start leva a porta da URL e restringe a escuta ao loopback.
    start = next(c for c in chamadas if c[0] == "pg_ctl.exe" and c[1] == "start")
    assert "-p 5433 -c listen_addresses=127.0.0.1" in start
    # O CREATE DATABASE veio depois da consulta de existência.
    assert "SELECT 1 FROM pg_database" in " ".join(chamadas[4])
    assert "CREATE DATABASE" in " ".join(chamadas[5])
    assert log  # log definido (mesmo que só referenciado)


def test_garantir_postgres_cluster_ja_no_ar_pula_initdb_e_start(tmp_path, monkeypatch):
    raiz = tmp_path
    _instalar_binarios(raiz)
    data_dir = raiz / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "PG_VERSION").write_text("16")
    (data_dir / "postmaster.pid").write_text("no-ar")

    monkeypatch.setattr(settings, "database_url", TESTE_URL)
    monkeypatch.setattr(settings, "pg_raiz", str(raiz))

    chamadas: list[list[str]] = []

    def run_fake(comando, **_):
        chamadas.append([Path(c).name for c in comando])
        ferramenta = Path(comando[0]).name
        if ferramenta == "pg_ctl.exe" and comando[1] == "status":
            return _Resultado(rc=0)  # já rodando
        if ferramenta == "pg_isready.exe":
            return _Resultado(rc=0)
        if ferramenta == "psql.exe":
            return _Resultado(rc=0, saida="1\n")  # banco já existe
        raise AssertionError(f"ferramenta inesperada: {ferramenta}")

    monkeypatch.setattr(pg.subprocess, "run", run_fake)

    pg.garantir_postgres()

    nomes = [c[0] for c in chamadas]
    assert "initdb.exe" not in nomes
    assert not any(c[:2] == ["pg_ctl.exe", "start"] for c in chamadas)
    # Só consultou existência do banco (não há CREATE DATABASE).
    assert nomes == ["pg_ctl.exe", "pg_isready.exe", "psql.exe"]


def test_garantir_postgres_sem_binarios_erro_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pg_raiz", str(tmp_path / "vazio"))
    monkeypatch.setattr(settings, "database_url", TESTE_URL)
    with pytest.raises(RuntimeError, match="não encontrado"):
        pg.garantir_postgres()


def test_falha_do_initdb_explode_com_a_saida(tmp_path, monkeypatch):
    raiz = tmp_path
    _instalar_binarios(raiz)
    monkeypatch.setattr(settings, "database_url", TESTE_URL)
    monkeypatch.setattr(settings, "pg_raiz", str(raiz))

    def run_fake(comando, **_):
        if Path(comando[0]).name == "initdb.exe":
            return _Resultado(rc=1, erro="locale invalido")
        raise AssertionError("não deveria chegar aqui")

    monkeypatch.setattr(pg.subprocess, "run", run_fake)
    with pytest.raises(RuntimeError, match="initdb"):
        pg.garantir_postgres()


def test_iniciar_nao_captura_a_saida_do_pg_ctl(monkeypatch, tmp_path):
    """Regressão do deadlock: o postgres.exe (neto, destacado) herda o pipe de
    stdout do `pg_ctl start` — com `capture_output` o `subprocess.run` espera
    um EOF que nunca chega e o daemon trava na primeira execução."""
    import subprocess

    capturado: dict = {}

    def run_fake(comando, **kwargs):
        capturado["kwargs"] = kwargs
        return _Resultado(rc=0)

    monkeypatch.setattr(pg.subprocess, "run", run_fake)
    pg._iniciar(tmp_path, tmp_path, tmp_path / "postgres.log", "127.0.0.1", 5433)
    assert capturado["kwargs"]["stdout"] is subprocess.DEVNULL
    assert capturado["kwargs"]["stderr"] is subprocess.DEVNULL
    assert capturado["kwargs"]["stdin"] is subprocess.DEVNULL


def test_iniciar_falha_inclui_a_cauda_do_log(tmp_path, monkeypatch):
    log = tmp_path / "postgres.log"
    log.write_text("... FATAL: porta em uso\n", encoding="utf-8")

    def run_fake(comando, **_):
        return _Resultado(rc=1)

    monkeypatch.setattr(pg.subprocess, "run", run_fake)
    with pytest.raises(RuntimeError, match="porta em uso"):
        pg._iniciar(tmp_path, tmp_path, log, "127.0.0.1", 5433)


def test_banco_com_nome_invalido_e_recusado(tmp_path, monkeypatch):
    _instalar_binarios(tmp_path)
    monkeypatch.setattr(settings, "pg_raiz", str(tmp_path))
    monkeypatch.setattr(
        settings,
        "database_url",
        'postgresql+psycopg://u:p@127.0.0.1/banco"mal"icioso',
    )
    with pytest.raises(RuntimeError, match="Nome de banco inválido"):
        pg.garantir_postgres()
