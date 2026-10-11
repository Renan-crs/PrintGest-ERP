"""Routers do módulo Agendamento — PRD §1.3 / telas_e_fluxos §1.3 (Calendário/Lista).

Compromissos de produção/entrega (tabela `agendamento`, já no `schema.sql`).
RBAC: operador+ (nível de movimento). Nenhum endpoint novo além do CRUD deste
módulo; nenhum endpoint existente é alterado.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import NivelAcesso, StatusAgenda, TipoAgenda
from app.schemas.agendamento import (
    AgendamentoCreate,
    AgendamentoOut,
    AgendamentoUpdate,
)
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.services import agendamento_service

router = APIRouter(
    prefix="/agendamento",
    tags=["agendamento"],
    dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))],
)


@router.get("", response_model=ListaResponse[AgendamentoOut])
def listar(
    db: DbDep,
    filial: FilialDep,
    inicio: datetime | None = Query(default=None, description="Início da janela (ISO)"),
    fim: datetime | None = Query(default=None, description="Fim da janela (ISO)"),
    tipo: TipoAgenda | None = None,
    status: StatusAgenda | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    itens, total = agendamento_service.listar(
        db,
        filial_id=filial,
        inicio=inicio,
        fim=fim,
        tipo=tipo,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("", response_model=ItemResponse[AgendamentoOut], status_code=201)
def criar(
    dados: AgendamentoCreate,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    return ItemResponse(
        data=agendamento_service.criar(
            db,
            filial_id=filial,
            usuario_id=usuario.id,
            dados=dados.model_dump(),
        )
    )


@router.get("/{item_id}", response_model=ItemResponse[AgendamentoOut])
def obter(item_id: int, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=agendamento_service.obter(db, filial_id=filial, item_id=item_id)
    )


@router.put("/{item_id}", response_model=ItemResponse[AgendamentoOut])
def atualizar(
    item_id: int,
    dados: AgendamentoUpdate,
    db: DbDep,
    filial: FilialDep,
):
    return ItemResponse(
        data=agendamento_service.atualizar(
            db,
            filial_id=filial,
            item_id=item_id,
            dados=dados.model_dump(exclude_unset=True),
        )
    )


@router.patch("/{item_id}/concluir", response_model=ItemResponse[AgendamentoOut])
def concluir(item_id: int, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=agendamento_service.concluir(db, filial_id=filial, item_id=item_id)
    )


@router.delete("/{item_id}", status_code=204)
def remover(item_id: int, db: DbDep, filial: FilialDep):
    agendamento_service.remover(db, filial_id=filial, item_id=item_id)


def registrar(api: APIRouter) -> None:
    api.include_router(router)
