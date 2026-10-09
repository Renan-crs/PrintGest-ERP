"""Fixtures da suíte — banco PostgreSQL dedicado + cliente HTTP.

Cria (uma vez por sessão) o banco `printgest_test`, aplica as migrations Alembic
`head` via subprocess (com PRINTGEST_DATABASE_URL apontando para o banco de teste)
e expõe um TestClient com o `get_db` sobrescrito para o banco de teste.

O bootstrap de empresa/filial/admin roda no startup do app via lifespan e é
idempotente — a primeira abertura do TestClient popula o banco de teste.
"""

import os
import subprocess
import sys
import asyncio
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# A suíte roda as migrations ela mesma (subprocesso, banco `printgest_test`).
# Desliga o auto-migrate do lifespan para nunca tocar no banco de desenvolvimento.
os.environ["PRINTGEST_AUTO_MIGRATE"] = "false"

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB = "printgest_test"
_HOST = "127.0.0.1:5432"
BASE_URL = f"postgresql+psycopg://printgest:printgest@{_HOST}"
TEST_DB_URL = f"{BASE_URL}/{TEST_DB}"


def _criar_banco() -> None:
    with psycopg.connect(f"host=127.0.0.1 port=5432 dbname=postgres user=printgest") as conn:
        conn.autocommit = True
        existe = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not existe:
            conn.execute(f'CREATE DATABASE "{TEST_DB}" OWNER printgest')


def _resetar_banco() -> None:
    with psycopg.connect(
        f"host=127.0.0.1 port=5432 dbname={TEST_DB} user=printgest"
    ) as conn:
        conn.autocommit = True
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _rodar_migrations() -> None:
    env = {**os.environ, "PRINTGEST_DATABASE_URL": TEST_DB_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def _banco_teste():
    _criar_banco()
    _resetar_banco()
    _rodar_migrations()
    return create_engine(TEST_DB_URL, pool_pre_ping=True)


@pytest.fixture()
def client(_banco_teste):
    from app import bootstrap, deps
    from app.db import SessionLocal

    SessionLocal.configure(bind=_banco_teste, expire_on_commit=False)
    factory = sessionmaker(
        bind=_banco_teste, autoflush=False, expire_on_commit=False
    )
    deps.SessionLocal = factory
    bootstrap.SessionLocal = factory

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    from app.main import app
    from app.deps import get_db
    from app.services import licensa_service

    # O loop de renovação (lifespan) fica inerte na suíte: testes de
    # licenciamento exercitam ativar/renovar com o HTTP mockado e controlam o
    # ESTADO explicitamente; a suíte legada opera "como licenciada".
    async def _loop_inerte() -> None:
        await asyncio.sleep(3600)

    _loop_original = licensa_service.loop_renovacao
    licensa_service.loop_renovacao = _loop_inerte
    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as c:
            licensa_service.ESTADO["modo_leitura"] = False
            yield c
    finally:
        licensa_service.loop_renovacao = _loop_original
        app.dependency_overrides.clear()


@pytest.fixture()
def admin_token(client):
    resp = client.post(
        "/v1/auth/login", json={"login": "admin", "senha": "admin123"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def auth(client, token):
    return {"Authorization": f"Bearer {token}"}