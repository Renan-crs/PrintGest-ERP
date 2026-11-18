"""Sync Agent — envio do outbox ao Neon (PRD v3.3 §5.4/§5.5).

- Lê eventos **pendentes** de `evento_sync` em ordem de `seq`, em lotes.
- Envia ao banco consolidado no Neon usando um **role por filial** com RLS
  (RF-SC-02): a URL vem do cofre (`cofre_sync`) e a sessão faz
  `SET LOCAL app.filial_id` antes do INSERT.
- Idempotente: `uuid` é a chave no destino (`ON CONFLICT DO NOTHING`), então
  reenvio após falha não duplica (RF-SY-02).
- Marca como enviados **somente** os uuids efetivamente aceitos.
- Sem internet os eventos acumulam; ao voltar, o envio retoma sem perda.
- Backoff exponencial com jitter após falhas; nunca bloqueia a operação.

NOTA: nenhuma credencial é logada. O destino é validado (psycopg com SSL).
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime

import psycopg
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import cofre_sync
from app.core.config import settings
from app.models.plataforma import EventoSync
from app.services import filial_service

# SQL de consolidação — executado no Neon com role da filial e RLS ativo.
# `set_config` aceita parâmetro (ao contrário de `SET LOCAL`, que exige
# literal e falharia com "syntax error at or near $1" no psycopg3).
# As duas instruções DEVEM ser executadas separadamente: psycopg3 usa
# prepared statements e rejeita múltiplos comandos numa só `execute()`.
_SET_FILIAL = "SELECT set_config('app.filial_id', %s::text, true)"
_INSERT = """
INSERT INTO consolidado.evento_sync
    (uuid, filial_id, entidade, entidade_id, operacao, payload, seq, criado_em)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
ON CONFLICT (uuid) DO NOTHING;
"""


class SyncNaoConfigurado(RuntimeError):
    """Nenhuma URL de consolidação cadastrada para a filial."""


def configurado(db: Session, filial_id: int) -> bool:
    # A URL consolidada é sempre por filial, guardada no cofre.
    return bool(cofre_sync.url(filial_id))


def _url_destino(filial_id: int) -> str:
    url = cofre_sync.url(filial_id)
    if not url:
        raise SyncNaoConfigurado(
            "Consolidação não configurada para esta filial."
        )
    return url


def _conectar(url: str):
    # sslmode=require por padrão (RF-SC-01: só conexões de saída TLS).
    if "sslmode=" not in url:
        separador = "&" if "?" in url else "?"
        url = f"{url}{separador}sslmode=require"
    return psycopg.connect(url, connect_timeout=10, autocommit=False)


def enviar_lote(
    db: Session,
    *,
    filial_id: int,
    eventos: list[EventoSync],
    conexao=None,
) -> dict:
    """Envia um lote. `conexao` é injetável nos testes (psycopg compatível)."""
    if not eventos:
        return {"enviados": 0, "erro": None}
    url = _url_destino(filial_id)
    dono = conexao is None
    conn = conexao or _conectar(url)
    aceitos: list[str] = []
    erro: str | None = None
    try:
        with conn.cursor() as cur:
            # is_local=True → vigente só nesta transação (equivale ao SET LOCAL).
            cur.execute(_SET_FILIAL, (str(filial_id),))
            for ev in eventos:
                cur.execute(
                    _INSERT,
                    (
                        ev.uuid,
                        filial_id,
                        ev.entidade,
                        ev.entidade_id,
                        ev.operacao,
                        __import__("json").dumps(ev.payload or {}, ensure_ascii=False),
                        ev.seq,
                        ev.criado_em,
                    ),
                )
                aceitos.append(ev.uuid)
        conn.commit()
    except Exception as exc:  # psycopg/rede — não expor detalhes com senha
        if dono:
            conn.rollback()
        erro = f"Falha no envio: {type(exc).__name__}."
        aceitos = []
    finally:
        if dono:
            conn.close()

    if aceitos:
        filial_service.marcar_enviados(db, filial_id=filial_id, uuids=aceitos)
    return {"enviados": len(aceitos), "erro": erro}


def sincronizar(db: Session, *, filial_id: int, conexao=None) -> dict:
    """Executa um ciclo: lê pendentes, envia e marca. Nunca lança para o loop."""
    if not configurado(db, filial_id):
        return {"ok": False, "motivo": "nao_configurado", "enviados": 0}
    pendentes, _ = filial_service.eventos(
        db, filial_id=filial_id, pendentes=True, limit=settings.sync_lote
    )
    if not pendentes:
        return {"ok": True, "motivo": "sem_pendencias", "enviados": 0}
    resultado = enviar_lote(
        db, filial_id=filial_id, eventos=pendentes, conexao=conexao
    )
    return {
        "ok": resultado["erro"] is None,
        "motivo": resultado["erro"] or "ok",
        "enviados": resultado["enviados"],
    }


def backoff(falhas: int) -> float:
    """Segundos até a próxima tentativa, com jitter ±%."""
    valores = [
        int(v)
        for v in settings.sync_backoff_segundos.split(",")
        if v.strip().isdigit()
    ] or [60, 300, 900, 3600]
    base = valores[min(falhas, len(valores) - 1)]
    jitter = max(0, settings.sync_jitter_percentual) / 100.0
    return base * (1 + random.uniform(-jitter, jitter))


def registrar_url(db: Session, *, filial_id: int, url: str | None) -> dict:
    """Configura a URL por filial (Admin). Nunca devolve a URL em claro."""
    if url and not url.lower().startswith(("postgresql://", "postgres://")):
        raise HTTPException(400, "A URL deve ser postgresql://… com TLS.")
    cofre_sync.definir_url(filial_id, url)
    return {
        "filial_id": filial_id,
        "configurado": bool(url),
        "url_mascarada": ("***" + url[-8:]) if url else None,
    }


def status(db: Session, *, filial_id: int) -> dict:
    info = filial_service.defasagem(db, filial_id=filial_id)
    return {
        **info,
        "configurado": configurado(db, filial_id),
        "intervalo_segundos": settings.sync_intervalo_segundos,
        "ultima_verificacao": datetime.now(UTC),
    }
