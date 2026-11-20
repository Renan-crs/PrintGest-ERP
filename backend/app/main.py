# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-PrintGest-Commercial
"""main — Local API Service PrintGest.

Licenciamento por **chave de produto** (RedGest Contrato C): o lifespan inicia o
loop de revalidação online (dentro de `licensa_service`) e um middleware
transversal bloqueia escritas (POST/PUT/PATCH/DELETE) com HTTP 423 enquanto a
licença estiver sem ativação, revogada/bloqueada/expirada ou com a tolerância
esgotada (modo de leitura). Rotas de licença, autenticação e documentação ficam
sempre liberadas para permitir a tela de ativação.
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api
from app.bootstrap import rodar_bootstrap
from app.core.config import settings
from app.core.migrations import aplicar_migrations
from app.services import financeiro_service, gating, licensa_service

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


async def _loop_fechamento_automatico_caixa() -> None:
    """Fecha caixas abertos automaticamente às 23:00 (hora local) se não fechados."""
    ultimo_dia: date | None = None
    while True:
        try:
            agora = datetime.now()
            # Janela das 23:00 às 23:59: antes exigia minute == 0, então um
            # restart após 23:00:59 ou um event loop ocupado pulava o dia.
            if agora.hour == 23 and ultimo_dia != agora.date():
                from app.db import SessionLocal

                db = SessionLocal()
                try:
                    fechados = financeiro_service.fechar_caixas_abertos_automaticamente(
                        db
                    )
                    ultimo_dia = agora.date()
                    if fechados:
                        logger.info(
                            "Fechamento automático de caixa às 23:00: %s caixa(s) fechado(s).",
                            fechados,
                        )
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha no fechamento automático de caixa")
        await asyncio.sleep(30)


async def _loop_sync_agent() -> None:
    """Sync Agent (RF-SY-02): envia pendências em lote, com backoff.

    Roda fora da requisição; falha de rede nunca derruba o serviço nem afeta
    a operação local. Usa uma sessão de banco por ciclo.
    """
    from app.db import SessionLocal
    from app.services import consolidacao_service, sync_service
    from app.services.tenants import filiais_do_tenant

    falhas = 0
    await asyncio.sleep(10)  # dá tempo ao bootstrap/migrations
    while True:
        try:
            db = SessionLocal()
            try:
                for filial_id in filiais_do_tenant(db):
                    if not sync_service.configurado(db, filial_id):
                        continue
                    resultado = sync_service.sincronizar(db, filial_id=filial_id)
                    logger.info("sync_agent filial=%s %s", filial_id, resultado)
                    if resultado.get("ok"):
                        falhas = 0
                    else:
                        falhas += 1
                    # PRD v3.3 §5.3/§5.4: subida + descida no mesmo ciclo.
                    # Cada etapa é isolada: falha de uma não impede as outras.
                    for nome, acao in (
                        ("mestres", consolidacao_service.descer_mestres),
                        ("resolucoes", consolidacao_service.descer_resolucoes),
                    ):
                        try:
                            descida = acao(db, filial_id=filial_id)
                            logger.info(
                                "sync_agent filial=%s descida=%s %s",
                                filial_id,
                                nome,
                                descida,
                            )
                        except Exception:
                            logger.exception(
                                "sync_agent falha na descida %s (filial=%s)",
                                nome,
                                filial_id,
                            )
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            falhas += 1
            logger.exception("Falha no Sync Agent")
        await asyncio.sleep(
            sync_service.backoff(falhas)
            if falhas
            else settings.sync_intervalo_segundos
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    # P17: falha cedo quando defaults de desenvolvimento estão ativos em produção.
    settings.validar_producao()
    # Aplica migrations pendentes (idempotente) — evita drift de schema do banco.
    aplicar_migrations()
    # Fase 1: garantia de empresa/filial/admin de fábrica no primeiro start.
    rodar_bootstrap()
    # Mantém o banco (Neon) acordado: sem o ping, o scale-to-zero do compute
    # derrubava as conexões do pool após ~5 min parado e a primeira ação do
    # usuário esperava o cold start (lentidão ao salvar / sessão "perdida").
    from app.db import iniciar_keepalive

    iniciar_keepalive()
    # Fase 4: mantém a licença renovada; sem ativação, apenas recalcula o modo.
    tarefa_renovacao = asyncio.create_task(licensa_service.loop_renovacao())
    tarefa_fechamento = asyncio.create_task(_loop_fechamento_automatico_caixa())
    # PRD v3.3: Sync Agent — esvazia o outbox para o Neon em background.
    tarefa_sync = asyncio.create_task(_loop_sync_agent())
    yield
    tarefa_sync.cancel()
    tarefa_fechamento.cancel()
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


# Gating por módulo ANTES do modo leitura no código: o modo leitura é a
# trava mais fundamental (licença) e, na pilha do Starlette, o ÚLTIMO
# middleware registrado é o mais externo — aqui ele roda primeiro.
@app.middleware("http")
async def _gating_modulos(request: Request, call_next):
    return await gating.controle_modulos(request, call_next)


@app.middleware("http")
async def controle_modo_leitura(request: Request, call_next):
    if request.method in {"GET", "HEAD", "OPTIONS"} or _caminho_permitido(
        request.url.path
    ):
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
