"""Routers do Dashboard (Tela Inicial) — resumo do dia por filial.

`GET /v1/dashboard/resumo` é acessível a qualquer usuário autenticado; os
campos operacionais (>= OPERADOR) e gerenciais (>= GERENTE) são filtrados
server-side dentro de `dashboard_service.resumo`. `dias` (7/30) controla a
janela das séries de vendas realizadas e faturamento previsto.
"""

from fastapi import APIRouter, Query

from app.deps import DbDep, FilialDep, UsuarioDep
from app.schemas.common import ItemResponse
from app.schemas.dashboard import DashboardResumoOut
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/resumo", response_model=ItemResponse[DashboardResumoOut])
def resumo_dashboard(
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
    dias: int = Query(default=7, ge=7, le=30),
) -> ItemResponse[DashboardResumoOut]:
    dados = dashboard_service.resumo(
        db,
        filial_id=filial,
        nivel=usuario.nivel_acesso,
        dias=dias,
    )
    return ItemResponse(data=dados)