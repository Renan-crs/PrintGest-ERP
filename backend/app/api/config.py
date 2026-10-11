"""Routers do módulo Configuração — PRD v2.0 §1.8 / telas_e_fluxos §1.8, §2.6.

RBAC: exclusivo do perfil **admin** (menu v2.1, grupo Sistema). Reúne os Dados
da Empresa / Personalização e o Reajuste de Preços em Bloco (simulação +
confirmação por senha, com trilha de auditoria em `preco_reajuste_historico`).
"""

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import NivelAcesso
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.config import (
    EmpresaOut,
    EmpresaUpdate,
    ReajusteAplicarIn,
    ReajusteHistoricoOut,
    ReajusteResultadoOut,
    ReajusteSimulacaoIn,
    ReajusteSimulacaoOut,
)
from app.services import config_service

router = APIRouter(
    prefix="/config",
    tags=["configuracao"],
    dependencies=[Depends(require_nivel(NivelAcesso.ADMIN))],
)


# ------------------------------------------------------------ empresa / dados
@router.get("/empresa", response_model=ItemResponse[EmpresaOut])
def empresa(db: DbDep, filial: FilialDep):
    return ItemResponse(data=config_service.empresa_atual(db, filial_id=filial))


@router.put("/empresa", response_model=ItemResponse[EmpresaOut])
def atualizar_empresa(payload: EmpresaUpdate, db: DbDep, filial: FilialDep):
    dados = payload.model_dump(exclude_unset=True)
    return ItemResponse(
        data=config_service.atualizar_empresa(db, filial_id=filial, dados=dados)
    )


# -------------------------------------------------------------------- reajuste
@router.get("/reajuste/historico", response_model=ListaResponse[ReajusteHistoricoOut])
def historico(
    db: DbDep,
    filial: FilialDep,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    itens, total = config_service.listar_historico(
        db, filial_id=filial, limit=limit, offset=offset
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("/reajuste/simular", response_model=ItemResponse[ReajusteSimulacaoOut])
def simular(payload: ReajusteSimulacaoIn, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=config_service.simular(
            db,
            filial_id=filial,
            criterio=payload.criterio,
            categoria_id=payload.categoria_id,
            tipo_reajuste=payload.tipo_reajuste,
            valor=payload.valor,
        )
    )


@router.post("/reajuste/aplicar", response_model=ItemResponse[ReajusteResultadoOut])
def aplicar(
    payload: ReajusteAplicarIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=config_service.aplicar(
            db,
            filial_id=filial,
            usuario=usuario,
            criterio=payload.criterio,
            categoria_id=payload.categoria_id,
            tipo_reajuste=payload.tipo_reajuste,
            valor=payload.valor,
            senha=payload.senha,
        )
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
