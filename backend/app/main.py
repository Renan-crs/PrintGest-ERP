"""main — Local API Service PrintGest.

Fase 4 (licenciamento `online_periodic`): o lifespan inicia o loop de renovação
(dentro de `licensa_service`) e um middleware transversal bloqueia escritas
(POST/PUT/PATCH/DELETE) com HTTP 423 enquanto a licença estiver sem ativação,
revogada ou com token vencido (modo de leitura). Rotas de licença, autenticação
e documentação ficam sempre liberadas para permitir a tela de ativação.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import api
from app.bootstrap import rodar_bootstrap
from app.core.config import settings
from app.services import licensa_service

_MSG_MODO_LEITURA = (
    "Sistema em modo de leitura: a licença está vencida, revogada ou ainda não "
    "foi ativada. As operações de alteração estão bloqueadas — ative a licença "
    "ou regularize a comunicação com o servidor de licenças."
)

# Em modo leitura só seguem livres: rotas de licença (para a tela de ativação e
# renovação), login/logout (usadas pela UI 1.x), autenticação de leitura (`/me`,
# já GET, mantido por clareza) e documentação. `/v1/auth/trocar-senha` é uma
# escrita e permanece bloqueada (423) no modo leitura.
_CAMINHOS_PERMITIDOS = (
    "/v1/auth/login",
    "/v1/auth/logout",
    "/v1/auth/me",
    "/v1/licenca",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _caminho_permitido(path: str) -> bool:
    return path.startswith(_CAMINHOS_PERMITIDOS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fase 1: garantia de empresa/filial/admin de fábrica no primeiro start.
    rodar_bootstrap()
    # Fase 4: mantém a licença renovada; sem ativação, apenas recalcula o modo.
    tarefa_renovacao = asyncio.create_task(licensa_service.loop_renovacao())
    yield
    tarefa_renovacao.cancel()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)


@app.middleware("http")
async def controle_modo_leitura(request: Request, call_next):
    if request.method in {"GET", "HEAD", "OPTIONS"} or _caminho_permitido(request.url.path):
        return await call_next(request)
    if not settings.licenca_desabilitada and licensa_service.ESTADO["modo_leitura"]:
        return JSONResponse(
            status_code=423,
            content={"detail": _MSG_MODO_LEITURA},
        )
    return await call_next(request)


app.include_router(api)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}