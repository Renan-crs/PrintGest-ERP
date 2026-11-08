"""Fixtures da suíte — banco PostgreSQL dedicado + cliente HTTP.

Cria (uma vez por sessão) o banco `printgest_test`, aplica as migrations Alembic
`head` via subprocess (com PRINTGEST_DATABASE_URL apontando para o banco de teste)
e expõe um TestClient com o `get_db` sobrescrito para o banco de teste.

O bootstrap de empresa/filial/admin roda no startup do app via lifespan e é
idempotente — a primeira abertura do TestClient popula o banco de teste.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# A suíte roda as migrations ela mesma (subprocesso, banco `printgest_test`).
# Desliga o auto-migrate do lifespan para nunca tocar no banco de desenvolvimento.
os.environ["PRINTGEST_AUTO_MIGRATE"] = "false"

# A suíte do Contrato C pressupõe o default `c`. O `.env` da máquina pode estar
# em piloto do Contrato B (`PRINTGEST_REDGEST_CONTRATO=b`) e não pode virar o
# contrato dos testes — os casos do Contrato B ligam a flag via monkeypatch.
os.environ["PRINTGEST_REDGEST_CONTRATO"] = "c"

# A suíte usa o admin de teste (`admin123`); não herda a senha do `.env` da
# máquina, que pode estar em piloto/produção.
os.environ["PRINTGEST_ADMIN_INICIAL_SENHA"] = "admin123"
# Instalações novas nascem com admin em primeiro acesso; a suíte precisa do
# admin já utilizável nas fixtures.
os.environ["PRINTGEST_ADMIN_INICIAL_PRIMEIRO_ACESSO"] = "false"

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB = "printgest_test"

# CI: o workflow fornece `DATABASE_URL` (serviço Postgres efêmero do GitHub
# Actions — banco descartável, pode ser zerado direto). Local: Postgres
# portable da `.dev` (auth trust), onde a suíte isola em `printgest_test`
# para nunca tocar no banco de desenvolvimento. Só aceitamos a env quando é
# Postgres: outras bases (ex.: `sqlite:///:memory:` de outro projeto na
# máquina) não servem para a suíte e precisam cair no default local.
_URL_CI = os.environ.get("DATABASE_URL", "").strip()
if _URL_CI.startswith("postgresql"):
    if "://" not in _URL_CI:
        _URL_CI = "postgresql://" + _URL_CI
    _BASE_CRUA = _URL_CI.rstrip("/")
    _ADMIN_CRUA = None  # o banco do CI já existe
    TEST_DB_URL_CRUA = _BASE_CRUA
else:
    _BASE_CRUA = "postgresql://printgest@127.0.0.1:5432/printgest"
    _ADMIN_CRUA = "postgresql://printgest@127.0.0.1:5432/postgres"
    TEST_DB_URL_CRUA = f"postgresql://printgest@127.0.0.1:5432/{TEST_DB}"

# SQLAlchemy exige o driver explícito; o psycopg.connect aceita a URL crua.
TEST_DB_URL = TEST_DB_URL_CRUA.replace("postgresql://", "postgresql+psycopg://", 1)

from app.core.config import settings


def _criar_banco() -> None:
    if _ADMIN_CRUA is None:
        return  # CI: o banco do serviço já existe
    with psycopg.connect(_ADMIN_CRUA) as conn:
        conn.autocommit = True
        existe = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not existe:
            conn.execute(f'CREATE DATABASE "{TEST_DB}" OWNER printgest')


def _resetar_banco() -> None:
    with psycopg.connect(TEST_DB_URL_CRUA) as conn:
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
    factory = sessionmaker(bind=_banco_teste, autoflush=False, expire_on_commit=False)
    deps.SessionLocal = factory
    bootstrap.SessionLocal = factory

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    from app.deps import get_db
    from app.main import app
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
    resp = client.post("/v1/auth/login", json={"login": "admin", "senha": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


@pytest.fixture
def caixa_admin(_banco_teste):
    """Caixa aberto para o usuário admin — vendas de balcão o exigem (M0).

    Abre no início e remove as linhas no fim (movimentos + caixa) para não
    vazar estado entre testes — o índice único (filial, usuário | status
    'aberto') impediria uma segunda abertura.
    """
    from app.db import SessionLocal
    from app.models.core import Usuario
    from app.models.financeiro import Caixa, MovimentoCaixa
    from app.services import financeiro_service

    db = SessionLocal()
    try:
        admin = (
            db.query(Usuario)
            .filter(Usuario.login == settings.admin_inicial_login)
            .first()
        )
        caixa = financeiro_service.caixa_aberto(
            db, filial_id=admin.filial_id, usuario_id=admin.id
        )
        criado = False
        if caixa is None:
            from app.schemas.financeiro import AbrirCaixaIn

            caixa = financeiro_service.abrir_caixa(
                db,
                filial_id=admin.filial_id,
                usuario_id=admin.id,
                dados=AbrirCaixaIn(valor_abertura=0, observacoes="caixa do teste"),
            )
            criado = True
        yield caixa
        if criado:
            db.query(MovimentoCaixa).filter(
                MovimentoCaixa.caixa_id == caixa.id
            ).delete()
            db.query(Caixa).filter(Caixa.id == caixa.id).delete()
            db.commit()
    finally:
        db.close()


def auth(client, token):
    return {"Authorization": f"Bearer {token}"}


def arte_aprovada(client, token, os_id: int) -> None:
    """Envia e aprova a arte da OS — libera a produção (M3, §3.5 gate).

    O status da OS passa a `aguardando_aprovacao` no upload e `aprovado`
    na decisão; usar antes de avançar para `producao` nos testes.
    """
    import io as _io

    resp = client.post(
        f"/v1/os/{os_id}/arte",
        headers=auth(client, token),
        files={"arquivo": ("arte.png", _io.BytesIO(b"PNG teste"), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    versao_id = resp.json()["data"]["id"]
    resp = client.post(
        f"/v1/os/{os_id}/arte/{versao_id}/decisao",
        headers=auth(client, token),
        json={"decisao": "aprovada"},
    )
    assert resp.status_code == 201, resp.text
