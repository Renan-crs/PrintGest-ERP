"""Router raiz da API — prefixo `/v1` com todos os módulos da Fase 1."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api import cadastros
from app.api.balcao import router as balcao_router
from app.api.dashboard import router as dashboard_router
from app.api.estoque import router as estoque_router
from app.api.licenca import router as licenca_router
from app.api.movimento import router as movimento_router
from app.api.usuarios import router as usuarios_router

api = APIRouter(prefix="/v1")

api.include_router(auth_router)
cadastros.registrar(api)
api.include_router(movimento_router)
api.include_router(balcao_router)
api.include_router(estoque_router)
api.include_router(usuarios_router)
api.include_router(licenca_router)
api.include_router(dashboard_router)


__all__ = ["api"]
