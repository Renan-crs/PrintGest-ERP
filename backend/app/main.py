"""main — Local API Service PrintGest.

Fase 4 (licenciamento `online_periodic`): o lifespan inicia o loop de renovação
(dentro de `licensa_service`) e um middleware transversal bloqueia escritas
(POST/PUT/PATCH/DELETE) com HTTP 423 enquanto a licença estiver sem ativação,
revogada ou com token vencido (modo de leitura). Rotas de licença, autenticação
e documentação ficam sempre liberadas para permitir a tela de ativação.
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api
from app.bootstrap import rodar_bootstrap
from app.core.config import settings
from app.services import licensa_service

logger = logging.getLogger("printgest")

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class _FiltroRequestId(logging.Filter):
    """Injeta o `request_id` da requisição corrente no registro de log (P15)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def _configurar_logging() -> None:
    """Logging básico (INFO) com correlação por requisição (P15)."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
            )
        )
        handler.addFilter(_FiltroRequestId())
        root.addHandler(handler)
    root.setLevel(logging.INFO)


_configurar_logging()

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
    # P17: falha cedo quando defaults de desenvolvimento estão ativos em produção.
    settings.validar_producao()
    # Fase 1: garantia de empresa/filial/admin de fábrica no primeiro start.
    rodar_bootstrap()
    # Fase 4: mantém a licença renovada; sem ativação, apenas recalcula o modo.
    tarefa_renovacao = asyncio.create_task(licensa_service.loop_renovacao())
    yield
    tarefa_renovacao.cancel()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

# CORS explícito (P20): vazio por padrão (o desktop não é navegador); habilite por
# ambiente via PRINTGEST_CORS_ORIGINS quando houver cliente web.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(Exception)
async def _erro_nao_tratado(request: Request, exc: Exception) -> JSONResponse:
    """Envelope de erro consistente e sem vazamento de stack trace (P4).

    `HTTPException` (4xx) continua tratada pelo handler padrão do FastAPI.
    """
    logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": "Erro interno do servidor."}
    )


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


@app.middleware("http")
async def contexto_requisicao(request: Request, call_next):
    """Correlaciona a requisição (X-Request-ID) e aplica security headers (P15/P20)."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = _request_id.set(rid)
    inicio = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - inicio) * 1000,
        )
        return response
    finally:
        _request_id.reset(token)


app.include_router(api)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "version": settings.version}