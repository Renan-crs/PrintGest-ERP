"""Fichas de consumo, custo/margem e baixa de produção (guia V2).

Somente operações aditivas e opt-in: itens sem ficha seguem o fluxo legado.
Baixa real exige OPERADOR+ (mesmo gate do módulo de estoque); cadastro de
ficha exige GERENTE+ (mesmo gate de preço de cadastro).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.cadastros import Produto
from app.models.enums import NivelAcesso
from app.models.producao import FichaConsumo, OsItemConsumo
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.producao import (
    BaixarConsumoIn,
    ConsumoOut,
    CustoServicoOut,
    FichaConsumoIn,
    FichaConsumoOut,
)
from app.services import custo_service, producao_service

router = APIRouter(prefix="/producao", tags=["produção"])


def _produto_no_escopo(db: Session, produto_id: int, filial_id: int) -> Produto:
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id, Produto.filial_id == filial_id)
        .first()
    )
    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado."
        )
    return produto


@router.get("/fichas")
def listar_fichas(
    db: DbDep, filial: FilialDep, produto_id: int | None = None
) -> ListaResponse[FichaConsumoOut]:
    query = db.query(FichaConsumo).filter(FichaConsumo.filial_id == filial)
    if produto_id is not None:
        query = query.filter(FichaConsumo.produto_id == produto_id)
    itens = query.order_by(FichaConsumo.id.desc()).limit(200).all()
    return ListaResponse(
        data=[FichaConsumoOut.model_validate(f) for f in itens],
        meta=MetaPaginacao(total=query.count(), limit=200, offset=0),
    )


@router.post(
    "/fichas",
    status_code=201,
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def criar_ficha(
    body: FichaConsumoIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
) -> ItemResponse[FichaConsumoOut]:
    produto = _produto_no_escopo(db, body.produto_id, filial)
    insumo = _produto_no_escopo(db, body.insumo_id, filial)
    if insumo.tipo.value != "produto" or not insumo.controla_estoque:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O insumo precisa ser um produto com controle de estoque.",
        )
    if body.vigencia_fim is not None and body.vigencia_inicio is not None:
        if body.vigencia_fim <= body.vigencia_inicio:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="vigencia_fim deve ser maior que vigencia_inicio.",
            )
    if produto.tipo.value == "servico" and produto.controla_estoque:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Serviço não pode controlar estoque.",
        )
    ficha = FichaConsumo(
        uuid=str(uuid.uuid4()),
        filial_id=filial,
        produto_id=produto.id,
        insumo_id=insumo.id,
        quantidade_por_unidade=body.quantidade_por_unidade,
        perda_percentual=body.perda_percentual,
        custo_processo_unitario=body.custo_processo_unitario,
        vigencia_inicio=body.vigencia_inicio or datetime.now(UTC),
        vigencia_fim=body.vigencia_fim,
        criado_por=usuario.id,
    )
    db.add(ficha)
    db.commit()
    db.refresh(ficha)
    return ItemResponse(data=FichaConsumoOut.model_validate(ficha))


@router.post(
    "/fichas/{ficha_id}/encerrar",
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def encerrar_ficha(
    ficha_id: int, db: DbDep, filial: FilialDep, _usuario: UsuarioDep
) -> ItemResponse[FichaConsumoOut]:
    ficha = (
        db.query(FichaConsumo)
        .filter(FichaConsumo.id == ficha_id, FichaConsumo.filial_id == filial)
        .first()
    )
    if ficha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ficha não encontrada."
        )
    ficha.vigencia_fim = datetime.now(UTC)
    db.commit()
    db.refresh(ficha)
    return ItemResponse(data=FichaConsumoOut.model_validate(ficha))


@router.get("/produtos/{produto_id}/custo")
def custo_do_produto(
    produto_id: int, db: DbDep, filial: FilialDep
) -> ItemResponse[CustoServicoOut]:
    """Custo/margem de referência (preço vigente em `produto.preco_venda`)."""
    produto = _produto_no_escopo(db, produto_id, filial)
    custo, consumo, alertas = custo_service.calcular_custo_no_banco(
        db, filial_id=filial, produto_id=produto_id
    )
    preco = produto.preco_venda or 0
    return ItemResponse(
        data=CustoServicoOut(
            custo_unitario=custo,
            margem_bruta=custo_service.calcular_margem_bruta(preco, custo),
            consumo_previsto=consumo,
            alertas=alertas,
        )
    )


@router.get("/os/{os_id}/itens/{item_id}/consumo")
def consumo_do_item(
    os_id: int, item_id: int, db: DbDep, filial: FilialDep
) -> ListaResponse[ConsumoOut]:
    itens = (
        db.query(OsItemConsumo)
        .filter(
            OsItemConsumo.filial_id == filial,
            OsItemConsumo.ordem_servico_item_id == item_id,
        )
        .all()
    )
    return ListaResponse(
        data=[ConsumoOut.model_validate(c) for c in itens],
        meta=MetaPaginacao(total=len(itens), limit=200, offset=0),
    )


@router.post("/os/{os_id}/itens/{item_id}/baixar-consumo")
def baixar_consumo(
    os_id: int,
    item_id: int,
    body: BaixarConsumoIn,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
) -> ListaResponse[ConsumoOut]:
    consumos = producao_service.baixar_consumo(
        db,
        filial_id=filial,
        os_id=os_id,
        item_id=item_id,
        usuario_id=usuario.id,
        body=body,
    )
    return ListaResponse(
        data=[ConsumoOut.model_validate(c) for c in consumos],
        meta=MetaPaginacao(total=len(consumos), limit=200, offset=0),
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router, dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))])
