"""Resolução de regras de preço persistidas (guia V1, RF-VR-08/12).

Precedência: tabela do cliente → tabela da filial → tabela padrão. Dentro da
mesma tabela vale a regra de maior `prioridade` e, em empate, a de vigência
mais recente. Somente regras `ativo=True` e vigentes na data da operação são
consideradas — uma regra antiga nunca é editada, apenas encerrada.

Todo filtro inclui a filial do inquilino: nenhuma consulta é global.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.precificacao import RegraPreco, TabelaPreco
from app.schemas.precificacao import RegraPrecoIn

ORIGEM_CLIENTE = "tabela_cliente"
ORIGEM_FILIAL = "tabela_filial"
ORIGEM_PADRAO = "tabela_padrao"


@dataclass(frozen=True)
class RegraResolvida:
    origem: str
    regra_id: int
    tabela_id: int
    regra: RegraPrecoIn
    vigencia_inicio: datetime
    vigencia_fim: datetime | None


def _tabelas_candidatas(
    db: Session, *, filial_id: int, cliente_id: int | None
) -> list[tuple[str, TabelaPreco]]:
    """Tabelas do inquilino, na ordem de precedência do guia."""
    candidatas: list[tuple[str, TabelaPreco]] = []
    if cliente_id is not None:
        tabela = (
            db.query(TabelaPreco)
            .filter(
                TabelaPreco.filial_id == filial_id,
                TabelaPreco.cliente_id == cliente_id,
                TabelaPreco.ativo.is_(True),
            )
            .order_by(TabelaPreco.id.desc())
            .first()
        )
        if tabela is not None:
            candidatas.append((ORIGEM_CLIENTE, tabela))
    tabela = (
        db.query(TabelaPreco)
        .filter(
            TabelaPreco.filial_id == filial_id,
            TabelaPreco.cliente_id.is_(None),
            TabelaPreco.padrao.is_(False),
            TabelaPreco.ativo.is_(True),
        )
        .order_by(TabelaPreco.id.desc())
        .first()
    )
    if tabela is not None:
        candidatas.append((ORIGEM_FILIAL, tabela))
    tabela = (
        db.query(TabelaPreco)
        .filter(
            TabelaPreco.filial_id == filial_id,
            TabelaPreco.padrao.is_(True),
            TabelaPreco.ativo.is_(True),
        )
        .order_by(TabelaPreco.id.desc())
        .first()
    )
    if tabela is not None:
        candidatas.append((ORIGEM_PADRAO, tabela))
    return candidatas


def resolver(
    db: Session,
    *,
    filial_id: int,
    produto_id: int | None,
    cliente_id: int | None = None,
    data: datetime | None = None,
) -> RegraResolvida | None:
    if produto_id is None:
        return None
    agora = data or datetime.now(UTC)
    for origem, tabela in _tabelas_candidatas(
        db, filial_id=filial_id, cliente_id=cliente_id
    ):
        regra = (
            db.query(RegraPreco)
            .filter(
                RegraPreco.tabela_preco_id == tabela.id,
                RegraPreco.produto_id == produto_id,
                RegraPreco.ativo.is_(True),
                RegraPreco.vigencia_inicio <= agora,
                or_(
                    RegraPreco.vigencia_fim.is_(None),
                    RegraPreco.vigencia_fim > agora,
                ),
            )
            .order_by(
                RegraPreco.prioridade.desc(), RegraPreco.vigencia_inicio.desc()
            )
            .first()
        )
        if regra is None:
            continue
        try:
            regra_in = RegraPrecoIn(
                preco_base=Decimal(str(regra.preco_base)),
                faixas=regra.faixas or [],
                modificadores=regra.modificadores or [],
                minimo=(
                    Decimal(str(regra.minimo)) if regra.minimo is not None else None
                ),
                modo_faixa=regra.modo_faixa,
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Regra de preço {regra.id} está malformada: {exc.errors()}",
            ) from exc
        return RegraResolvida(
            origem=origem,
            regra_id=regra.id,
            tabela_id=tabela.id,
            regra=regra_in,
            vigencia_inicio=regra.vigencia_inicio,
            vigencia_fim=regra.vigencia_fim,
        )
    return None
