"""Estações por servidor (PRD v3.3 §4.12).

Estação NÃO é licenciada individualmente: ela só se registra no servidor e é
contada se acessou nos últimos 7 dias. O limite `max_estacoes` vale por
servidor (filial) e é aplicado no registro — a 6ª em plano de 5 recebe 409.
Sem entitlements, usa o último valor conhecido ou 5 (RF-ES-05).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.plataforma import Estacao
from app.services import licensa_service

DIAS_ATIVA = 7
LIMITE_PADRAO = 5


def limite(db: Session, *, filial_id: int) -> int:
    """`max_estacoes` dos entitlements, com fallback determinístico."""
    sit = licensa_service.situacao(db)
    valor = sit.get("limite_estacoes")
    if valor is None:
        lic = licensa_service._licenca_local(db)
        ents = (getattr(lic, "entitlements", None) or {}) if lic is not None else {}
        valor = ents.get("max_estacoes")
    try:
        resultado = int(valor) if valor is not None else LIMITE_PADRAO
    except (TypeError, ValueError):
        resultado = LIMITE_PADRAO
    return max(1, resultado)


def ativas(db: Session, *, filial_id: int) -> list[Estacao]:
    corte = datetime.now(UTC) - timedelta(days=DIAS_ATIVA)
    return (
        db.query(Estacao)
        .filter(
            Estacao.filial_id == filial_id,
            Estacao.ultimo_acesso >= corte,
        )
        .order_by(Estacao.ultimo_acesso.desc())
        .all()
    )


def registrar(
    db: Session, *, filial_id: int, nome: str, fingerprint: str
) -> Estacao:
    """Registra (ou atualiza o acesso de) uma estação. 409 se no limite."""
    fp = fingerprint.strip().lower()[:64]
    atual = (
        db.query(Estacao)
        .filter(Estacao.filial_id == filial_id, Estacao.fingerprint == fp)
        .first()
    )
    agora = datetime.now(UTC)
    if atual is not None:
        atual.nome = nome.strip()[:120] or atual.nome
        atual.ultimo_acesso = agora
        db.commit()
        db.refresh(atual)
        return atual

    limite_atual = limite(db, filial_id=filial_id)
    if len(ativas(db, filial_id=filial_id)) >= limite_atual:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "codigo": "ESTACAO_LIMITE_EXCEDIDO",
                "mensagem": (
                    f"Limite de {limite_atual} estações atingido neste servidor. "
                    "Remova uma estação inativa para liberar vaga."
                ),
            },
        )
    estacao = Estacao(
        filial_id=filial_id,
        nome=nome.strip()[:120] or "Estação",
        fingerprint=fp,
        ultimo_acesso=agora,
    )
    db.add(estacao)
    db.commit()
    db.refresh(estacao)
    return estacao


def listar(db: Session, *, filial_id: int) -> dict:
    corte = datetime.now(UTC) - timedelta(days=DIAS_ATIVA)
    linhas = (
        db.query(Estacao)
        .filter(Estacao.filial_id == filial_id)
        .order_by(Estacao.ultimo_acesso.desc())
        .all()
    )
    total = len([e for e in linhas if e.ultimo_acesso >= corte])
    limite_atual = limite(db, filial_id=filial_id)
    agora = datetime.now(UTC)
    itens = []
    for e in linhas:
        ativa = e.ultimo_acesso >= corte
        itens.append(
            {
                "id": e.id,
                "filial_id": e.filial_id,
                "nome": e.nome,
                "fingerprint": e.fingerprint[:12],
                "ultimo_acesso": e.ultimo_acesso,
                "criado_em": e.criado_em,
                "ativa": ativa,
                "dias_inativa": max(0, (agora - e.ultimo_acesso).days),
            }
        )
    return {
        "total": total,
        "limite": limite_atual,
        "vagas": max(0, limite_atual - total),
        "estacoes": itens,
    }


def remover(db: Session, *, item_id: int, filial_id: int) -> None:
    estacao = (
        db.query(Estacao)
        .filter(Estacao.id == item_id, Estacao.filial_id == filial_id)
        .first()
    )
    if estacao is None:
        raise HTTPException(404, "Estação não encontrada.")
    db.delete(estacao)
    db.commit()
