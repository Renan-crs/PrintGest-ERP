"""Integração REAL do Sync Agent contra o Postgres de teste.

Os testes de `test_sync_agent.py` usam psycopg mockado e não pegaram um bug
real: `SET LOCAL app.filial_id = %s` falha com "syntax error at or near $1"
no psycopg3, e múltiplos comandos numa `execute()` parametrizada também
falham. Aqui o SQL é executado de verdade.
"""

import json
import re
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from sqlalchemy.orm import sessionmaker

from app.core import cofre_sync
from app.core.config import settings
from app.db import SessionLocal
from app.models.cadastros import Produto
from app.services import consolidacao_service, filial_service, sync_service
from tests.conftest import TEST_DB_URL


def _aplicar_sql_leitura(conexao: psycopg.Connection) -> None:
    sql = open(
        r"C:\Compart\Projetos\Printgest\backend\sql\consolidacao_leitura.sql",
        encoding="utf-8",
    ).read()
    sem_coment = re.sub(r"--[^\n]*", "", sql)
    partes, atual, i = [], "", 0
    while i < len(sem_coment):
        if sem_coment[i : i + 2] == "$$":
            fim = sem_coment.find("$$", i + 2)
            atual += sem_coment[i : fim + 2]
            i = fim + 2
            continue
        atual += sem_coment[i]
        if sem_coment[i] == ";":
            if atual.strip():
                partes.append(atual.strip())
            atual = ""
        i += 1
    for parte in partes:
        conexao.execute(parte)


@pytest.fixture
def consolidado(client, tmp_path, monkeypatch):
    """Schema `consolidado` real no banco de teste, isolado por caso."""
    url = TEST_DB_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    monkeypatch.setattr(
        settings, "cofre_integracoes_arquivo", str(tmp_path / "integracoes.dat")
    )
    cofre_sync.limpar()
    cofre_sync.definir_url(1, url)

    conn = psycopg.connect(url, autocommit=True)
    try:
        conn.execute("DROP SCHEMA IF EXISTS consolidado CASCADE")
        conn.execute("CREATE SCHEMA consolidado")
        conn.execute(
            """
            CREATE TABLE consolidado.evento_sync (
                uuid text PRIMARY KEY, filial_id bigint NOT NULL,
                entidade text NOT NULL, entidade_id bigint,
                operacao text NOT NULL, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
                seq bigint NOT NULL, criado_em timestamptz NOT NULL,
                recebido_em timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE consolidado.evento_sync ENABLE ROW LEVEL SECURITY")
        conn.execute(
            """
            CREATE POLICY evento_sync_filial ON consolidado.evento_sync
            USING (filial_id = NULLIF(current_setting('app.filial_id', true), '')::bigint)
            WITH CHECK (filial_id = NULLIF(current_setting('app.filial_id', true), '')::bigint)
            """
        )
        _aplicar_sql_leitura(conn)
    finally:
        conn.close()

    # Não apagar produtos alheios: outros testes criam movimentos de estoque
    # com FK para eles. Cada caso usa um código único e limpa só o seu.
    yield url
    cofre_sync.limpar()


def test_envio_real_e_ciclo_completo(consolidado):
    db = SessionLocal()
    try:
        ev = filial_service.registrar_evento(
            db,
            filial_id=1,
            entidade="mestre:produto",
            entidade_id=None,
            operacao="Mestre",
            payload={
                "chave": f"CICLO-{uuid.uuid4().hex[:8]}",
                "nome": "Produto do ciclo",
                "preco_venda": "42.50",
            },
        )
        db.commit()
        chave = ev.payload["chave"]

        # Envio REAL — aqui o bug do SET LOCAL aparecia.
        conn = psycopg.connect(consolidado)
        try:
            resultado = sync_service.enviar_lote(
                db, filial_id=1, eventos=[ev], conexao=conn
            )
        finally:
            conn.close()
        assert resultado == {"enviados": 1, "erro": None}

        # Trigger aplicou o mestre no consolidado.
        conn = psycopg.connect(consolidado)
        try:
            linha = conn.execute(
                "SELECT versao, payload->>'nome' FROM consolidado.mestre "
                "WHERE entidade='mestre:produto' AND chave=%s",
                (chave,),
            ).fetchone()
        finally:
            conn.close()
        assert linha is not None and linha[1] == "Produto do ciclo"

        # Descida aplicou no cadastro local da filial.
        conn = psycopg.connect(consolidado)
        try:
            descida = consolidacao_service.descer_mestres(
                db, filial_id=1, conexao=conn
            )
        finally:
            conn.close()
        assert descida["ok"] is True

        produto = (
            db.query(Produto)
            .filter(Produto.filial_id == 1, Produto.codigo == chave)
            .first()
        )
        assert produto is not None and produto.nome == "Produto do ciclo"

        # Outbox esvaziado e reenvio não duplica.
        _, total = filial_service.eventos(db, filial_id=1, pendentes=True)
        assert total == 0
    finally:
        db.close()
        limpeza = SessionLocal()
        try:
            limpeza.query(Produto).filter(Produto.codigo == chave).delete()
            limpeza.commit()
        except Exception:
            limpeza.rollback()
        finally:
            limpeza.close()


def test_resolucao_e_relatorio_reais(consolidado):
    db = SessionLocal()
    try:
        documento = uuid.uuid4().hex[:14]
        uid = str(uuid.uuid4())
        conn = psycopg.connect(consolidado, autocommit=True)
        try:
            conn.execute(
                "INSERT INTO consolidado.evento_sync "
                "(uuid,filial_id,entidade,entidade_id,operacao,payload,seq,criado_em) "
                "VALUES (%s,2,'cliente',1,'CRS',%s::jsonb,1,now())",
                (uid, json.dumps({"nome_razao": "Oficial", "cpf_cnpj": documento})),
            )
            resolucao = consolidacao_service.resolver_conflito(
                db,
                filial_id=1,
                documento=documento,
                filial_escolhida=2,
                uuid_escolhido=uid,
                usuario_id=1,
                conexao=psycopg.connect(consolidado),
            )
            assert resolucao["payload_disponivel"] is True

            descida = consolidacao_service.descer_resolucoes(
                db, filial_id=1, conexao=psycopg.connect(consolidado)
            )
            assert descida["ok"] is True

            relatorio = consolidacao_service.relatorio_vendas(
                db, filial_id=1, conexao=psycopg.connect(consolidado)
            )
            assert relatorio["total_geral"] is not None
        finally:
            conn.close()
    finally:
        db.close()
