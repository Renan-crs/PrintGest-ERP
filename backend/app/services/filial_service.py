"""Filiais e outbox de sincronização (PRD v3.3 §5).

A licença é por servidor: `filial.instalacao_id` e `filial.papel` são gravados
na ativação (o papel vem do RedGest — RF-FL-07). Toda escrita relevante gera
um `evento_sync` na mesma transação da chamada (RF-SY-01); `uuid` é a chave de
idempotência e `seq` ordena a fila por filial.

NOTA DE ESCOPO: a consolidação real (Sync Agent → Neon com RLS) depende de
infraestrutura/credenciais por filial e é a próxima fase. Aqui entregamos a
fundação — outbox persistente, fila consultável e metadados de instalação.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.core import Filial
from app.models.plataforma import EventoSync
from app.services import tenants

PAPEL_MATRIZ = "MATRIZ"
PAPEL_FILIAL = "FILIAL"


def _filial(db: Session, filial_id: int) -> Filial:
    filial = db.get(Filial, filial_id)
    if filial is None:
        raise HTTPException(404, "Filial não encontrada.")
    return filial


def listar(db: Session, *, filial_id: int) -> list[dict]:
    """Filiais da MESMA empresa do tenant (nunca de outra empresa)."""
    atual = _filial(db, filial_id)
    linhas = (
        db.query(Filial)
        .filter(Filial.empresa_id == atual.empresa_id)
        .order_by(Filial.id)
        .all()
    )
    return [
        {
            "id": f.id,
            "empresa_id": f.empresa_id,
            "nome": f.nome,
            "cnpj": f.cnpj,
            "instalacao_id": f.instalacao_id,
            "papel": f.papel,
            "ativa": f.ativa,
            "criada_em": f.created_at,
            "_local": f.id == filial_id,
        }
        for f in linhas
    ]


def atualizar(
    db: Session, *, filial_id: int, dados: dict, usuario_id: int
) -> dict:
    filial = _filial(db, filial_id)
    if "papel" in dados and dados["papel"] is not None:
        papel = str(dados["papel"]).strip().upper()
        if papel not in (PAPEL_MATRIZ, PAPEL_FILIAL):
            raise HTTPException(400, "papel deve ser MATRIZ ou FILIAL.")
        dados["papel"] = papel
    for chave, valor in dados.items():
        if valor is not None:
            setattr(filial, chave, valor)
    registrar_evento(
        db,
        filial_id=filial_id,
        entidade="filial",
        entidade_id=filial.id,
        operacao="ATUALIZAR",
        payload={k: v for k, v in dados.items() if k != "papel"},
    )
    db.commit()
    db.refresh(filial)
    return {
        "id": filial.id,
        "empresa_id": filial.empresa_id,
        "nome": filial.nome,
        "cnpj": filial.cnpj,
        "instalacao_id": filial.instalacao_id,
        "papel": filial.papel,
        "ativa": filial.ativa,
        "criada_em": filial.created_at,
    }


def vincular_instalacao(
    db: Session, *, filial_id: int, instalacao_id: str, papel: str
) -> None:
    """Usado pela ativação (RF-FL-08) — semeldição via API aberta."""
    filial = _filial(db, filial_id)
    filial.instalacao_id = instalacao_id
    filial.papel = papel
    db.commit()


def _proximo_seq(db: Session, filial_id: int) -> int:
    atual = (
        db.query(func.coalesce(func.max(EventoSync.seq), 0))
        .filter(EventoSync.filial_id == filial_id)
        .scalar()
    )
    return int(atual or 0) + 1


def registrar_evento(
    db: Session,
    *,
    filial_id: int,
    entidade: str,
    entidade_id: int | None,
    operacao: str,
    payload: dict | None = None,
    uuid: str | None = None,
) -> EventoSync:
    """Enfileira um evento (sem commit) — a transação é do chamador.

    Idempotente: repetir o mesmo `uuid` devolve o evento já existente
    (RF-SY-02: entrega pelo menos uma vez, aplicação idempotente).
    """
    chave = uuid or str(uuid4())
    existente = (
        db.query(EventoSync).filter(EventoSync.uuid == chave).first()
    )
    if existente is not None:
        return existente
    evento = EventoSync(
        uuid=chave,
        filial_id=filial_id,
        entidade=entidade,
        entidade_id=entidade_id,
        operacao=operacao,
        payload=payload or {},
        seq=_proximo_seq(db, filial_id),
        criado_em=datetime.utcnow(),
    )
    db.add(evento)
    return evento


def eventos(
    db: Session,
    *,
    filial_id: int,
    pendentes: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[EventoSync], int]:
    query = db.query(EventoSync).filter(EventoSync.filial_id == filial_id)
    if pendentes is True:
        query = query.filter(EventoSync.enviado_em.is_(None))
    elif pendentes is False:
        query = query.filter(EventoSync.enviado_em.isnot(None))
    total = query.count()
    linhas = (
        query.order_by(EventoSync.seq, EventoSync.id).limit(limit).offset(offset).all()
    )
    return linhas, total


def marcar_enviados(db: Session, *, filial_id: int, uuids: list[str]) -> int:
    if not uuids:
        return 0
    agora = datetime.utcnow()
    n = (
        db.query(EventoSync)
        .filter(
            EventoSync.filial_id == filial_id,
            EventoSync.uuid.in_(uuids),
            EventoSync.enviado_em.is_(None),
        )
        .update({EventoSync.enviado_em: agora}, synchronize_session=False)
    )
    db.commit()
    return n


def defasagem(db: Session, *, filial_id: int) -> dict:
    """Último evento enviado — usado no painel de saúde."""
    ultimo = (
        db.query(func.max(EventoSync.enviado_em))
        .filter(EventoSync.filial_id == filial_id)
        .scalar()
    )
    pendentes = (
        db.query(func.count(EventoSync.id))
        .filter(
            EventoSync.filial_id == filial_id,
            EventoSync.enviado_em.is_(None),
        )
        .scalar()
        or 0
    )
    return {"ultimo_envio": ultimo, "pendentes": int(pendentes)}
