"""Routers do módulo Estoque — PRD v2.0 §1.3/§1.4, roadmap item 8 (mockups 4.1–4.3).

Nível mínimo de acesso: OPERADOR (consulta de saldos, movimentação manual e
relatório de reposição são operacionais). A movimentação manual grava o kardex
com origem `ajuste_manual`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import NivelAcesso, TipoMovEstoque
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.estoque import (
    EstoqueLinhaOut,
    EstoqueResumoOut,
    KardexOut,
    MovimentacaoOut,
    MovimentarIn,
    ReposicaoOut,
)
from app.services import estoque_service

router = APIRouter(
    prefix="/estoque",
    tags=["estoque"],
    dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))],
)


@router.get("", response_model=ListaResponse[EstoqueLinhaOut])
def consultar(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    categoria_id: int | None = None,
    abaixo_minimo: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse[EstoqueLinhaOut]:
    itens, total = estoque_service.consultar(
        db,
        filial_id=filial,
        q=q,
        categoria_id=categoria_id,
        abaixo_minimo=abaixo_minimo,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.get("/resumo", response_model=ItemResponse[EstoqueResumoOut])
def resumo(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    categoria_id: int | None = None,
    abaixo_minimo: bool = False,
) -> ItemResponse[EstoqueResumoOut]:
    return ItemResponse(
        data=estoque_service.resumo(
            db,
            filial_id=filial,
            q=q,
            categoria_id=categoria_id,
            abaixo_minimo=abaixo_minimo,
        )
    )


@router.get("/reposicao", response_model=ListaResponse[ReposicaoOut])
def reposicao(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    apenas_abaixo: bool = True,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse[ReposicaoOut]:
    itens, total = estoque_service.reposicao(
        db,
        filial_id=filial,
        q=q,
        apenas_abaixo=apenas_abaixo,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("/movimentar", response_model=ItemResponse[MovimentacaoOut])
def movimentar(
    payload: MovimentarIn,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
) -> ItemResponse[MovimentacaoOut]:
    movimento, saldo = estoque_service.movimentar(
        db, filial_id=filial, usuario_id=usuario.id, dados=payload
    )
    return ItemResponse(data=MovimentacaoOut(movimento=movimento, saldo=saldo))


@router.get("/{produto_id}/kardex", response_model=ListaResponse[KardexOut])
def kardex(
    produto_id: int,
    db: DbDep,
    filial: FilialDep,
    tipo: TipoMovEstoque | None = None,
    data_inicio: datetime | None = None,
    data_fim: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse[KardexOut]:
    itens, total = estoque_service.listar_kardex(
        db,
        filial_id=filial,
        produto_id=produto_id,
        tipo=tipo,
        data_inicio=data_inicio,
        data_fim=data_fim,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )
