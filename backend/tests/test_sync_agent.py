"""Sync Agent (PRD v3.3 §5.4): outbox -> Neon com RLS e idempotência.

Conexão psycopg é mockada: nenhum acesso real ao Neon.
"""

import json
import uuid

import pytest
from app.core import cofre_sync
from app.core.config import settings
from app.db import SessionLocal
from app.models.plataforma import EventoSync
from app.services import filial_service, sync_service
from tests.conftest import auth

FILIAL = 1
URL = "postgresql://user:pass@ep-test.neon.tech/consolidado?sslmode=require"


@pytest.fixture(autouse=True)
def _limpar(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_sync.limpar()
    db = SessionLocal()
    try:
        db.query(EventoSync).delete()
        db.commit()
    finally:
        db.close()
    yield
    cofre_sync.limpar()


class _Cursor:
    def __init__(self, registrar):
        self.registrar = registrar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.registrar.append((sql, params))


class _Conexao:
    def __init__(self):
        self.comandos = []
        self.commitado = False
        self.fechado = False

    def cursor(self):
        return _Cursor(self.comandos)

    def commit(self):
        self.commitado = True

    def rollback(self):
        self.commitado = False

    def close(self):
        self.fechado = True


def test_sem_configuracao_nao_envia(client, admin_token):
    db = SessionLocal()
    ev = filial_service.registrar_evento(
        db, filial_id=FILIAL, entidade="venda", entidade_id=1,
        operacao="CRS", payload={"total": "1.00"},
    )
    db.commit()
    res = sync_service.sincronizar(db, filial_id=FILIAL)
    assert res["ok"] is False and res["motivo"] == "nao_configurado"
    assert ev.enviado_em is None


def test_envia_lote_com_rls_e_marca_enviados(client, admin_token):
    cofre_sync.definir_url(FILIAL, URL)
    db = SessionLocal()
    for i in range(3):
        filial_service.registrar_evento(
            db, filial_id=FILIAL, entidade="venda", entidade_id=i,
            operacao="CRS", payload={"n": i},
        )
    db.commit()

    conn = _Conexao()
    resultado = sync_service.sincronizar(db, filial_id=FILIAL, conexao=conn)
    assert resultado == {"ok": True, "motivo": "ok", "enviados": 3}
    assert conn.commitado
    assert not conn.fechado  # conexão injetada pertence ao chamador
    # 1 set_config (RLS) + 3 INSERTs — eram 3 comandos antes da correção do
    # SET LOCAL, que falhava com "syntax error at or near $1" no psycopg3.
    assert len(conn.comandos) == 4

    sql_rls, params_rls = conn.comandos[0]
    assert "set_config('app.filial_id'" in sql_rls
    assert params_rls == (str(FILIAL),)

    sql, params = conn.comandos[1]
    assert "consolidado.evento_sync" in sql
    assert "ON CONFLICT (uuid) DO NOTHING" in sql
    assert params[1] == FILIAL  # filial_id (após o uuid)
    assert json.loads(params[5]) == {"n": 0}

    pendentes, total = filial_service.eventos(
        db, filial_id=FILIAL, pendentes=True
    )
    assert total == 0

    # Reexecutar não reenvia nada (idempotente no outbox local).
    conn2 = _Conexao()
    assert sync_service.sincronizar(
        db, filial_id=FILIAL, conexao=conn2
    )["motivo"] == "sem_pendencias"
    assert conn2.comandos == []


def test_falha_de_rede_nao_marca_como_enviado(client, admin_token):
    cofre_sync.definir_url(FILIAL, URL)
    db = SessionLocal()
    filial_service.registrar_evento(
        db, filial_id=FILIAL, entidade="os", entidade_id=9,
        operacao="UPD", payload={},
    )
    db.commit()

    class _Falha(_Conexao):
        def cursor(self):
            raise RuntimeError("conexão caiu")

    resultado = sync_service.sincronizar(
        db, filial_id=FILIAL, conexao=_Falha()
    )
    assert resultado["ok"] is False
    assert "nao" in resultado["motivo"] or "Falha" in resultado["motivo"]
    _, total = filial_service.eventos(db, filial_id=FILIAL, pendentes=True)
    assert total == 1  # permanece para reenvio


def test_configuracao_url_mascarada_e_admin_only(client, admin_token):
    h = auth(client, admin_token)
    r = client.put(
        "/v1/plataforma/sync/config", headers=h, json={"url": URL}
    )
    assert r.status_code == 200, r.text
    dados = r.json()["data"]
    assert dados["configurado"] is True
    assert dados["url_mascarada"].endswith(URL[-8:])
    assert "pass" not in str(dados)

    # URL inválida
    assert client.put(
        "/v1/plataforma/sync/config", headers=h, json={"url": "ftp://x"}
    ).status_code == 400

    status = client.get("/v1/plataforma/sync/status", headers=h).json()["data"]
    assert status["configurado"] is True
    assert status["intervalo_segundos"] == settings.sync_intervalo_segundos

    from tests.test_fiscal import _token_de

    gerente = auth(client, _token_de(client, admin_token, "gerente"))
    assert client.get(
        "/v1/plataforma/sync/config", headers=gerente
    ).status_code == 403


def test_backoff_com_jitter():
    vals = [sync_service.backoff(i) for i in range(4)]
    assert vals[0] >= 40 and vals[0] <= 80   # 60 ±20%
    assert vals[3] >= 2880 and vals[3] <= 4320  # 3600 ±20%
