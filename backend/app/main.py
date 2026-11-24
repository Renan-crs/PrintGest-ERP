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
import os
import sys
from pathlib import Path
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api
from app.bootstrap import rodar_bootstrap
from app.core.config import settings
from app.core.migrations import aplicar_migrations
from app.services import financeiro_service, gating, licensa_service

from app.core.log_seguranca import (  # noqa: E402
    FiltroRequestId as _FiltroRequestId,
    _LOG_FORMAT,
    request_id as _request_id,
    sanitizar,
)

logger = logging.getLogger("printgest")


def _configurar_logging() -> None:
    """Log detalhado e sanitizado em arquivo rotativo + console.

    - nível configurável por `PRINTGEST_LOG_NIVEL` (padrão INFO);
    - arquivo configurável por `PRINTGEST_LOG_ARQUIVO`
      (padrão `logs/printgest-api.log`);
    - todos os handlers recebem `request_id` e `FiltroSeguranca`;
    - idempotente: não duplica handlers já instalados por `run_server.py`.
    """
    from logging.handlers import RotatingFileHandler

    from app.core.log_seguranca import FiltroSeguranca

    root = logging.getLogger()
    nivel = os.environ.get("PRINTGEST_LOG_NIVEL", "INFO").upper()
    root.setLevel(getattr(logging, nivel, logging.INFO))

    filtros = (_FiltroRequestId(), FiltroSeguranca())
    formatador = logging.Formatter(_LOG_FORMAT)

    if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
        caminho = Path(os.environ.get(
            "PRINTGEST_LOG_ARQUIVO", "logs/printgest-api.log"
        ))
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            arquivo = RotatingFileHandler(
                caminho,
                maxBytes=int(os.environ.get("PRINTGEST_LOG_MAX_MB", "5")) * 1024 * 1024,
                backupCount=int(os.environ.get("PRINTGEST_LOG_BACKUPS", "3")),
                encoding="utf-8",
            )
            arquivo.setFormatter(formatador)
            for filtro in filtros:
                arquivo.addFilter(filtro)
            root.addHandler(arquivo)
        except OSError:
            pass  # log é best-effort: disco cheio/permissão não derruba a API

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        console = logging.StreamHandler(stream=sys.stderr or open(os.devnull, "w"))
        console.setFormatter(formatador)
        for filtro in filtros:
            console.addFilter(filtro)
        root.addHandler(console)

    # Handlers criados antes (ex.: run_server.py) também precisam dos filtros.
    for handler in root.handlers:
        if not any(isinstance(f, FiltroSeguranca) for f in handler.filters):
            handler.addFilter(FiltroSeguranca())
        if not any(isinstance(f, _FiltroRequestId) for f in handler.filters):
            handler.addFilter(_FiltroRequestId())
        handler.setFormatter(formatador)


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
    # Simulador de preço: cálculo puro, não grava nada (guia de variações §11.9).
    "/v1/variacoes/preco/simular",
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


def _contexto_auditoria() -> tuple[int | None, int | None]:
    """Filial/usuário do contexto preenchidos pelas dependencies."""
    from app.deps import filial_logada, usuario_logado

    return filial_logada.get(), usuario_logado.get()


@app.exception_handler(StarletteHTTPException)
async def _erro_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Todo 4xx/5xx explícito vira uma linha detalhada no log."""
    filial, usuario = _contexto_auditoria()
    logger.error(
        "HTTP %s %s %s | filial=%s usuario=%s tipo=%s detail=%s",
        exc.status_code,
        request.method,
        request.url.path,
        filial,
        usuario,
        type(exc).__name__,
        sanitizar(exc.detail),
        exc_info=(type(exc), exc, exc.__traceback__) if exc.__traceback__ else None,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": jsonable_encoder(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _erro_validacao(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Erros 422 do Pydantic também são registrados com os campos afetados."""
    filial, usuario = _contexto_auditoria()
    detalhes = jsonable_encoder(sanitizar(exc.errors()))
    logger.error(
        "HTTP 422 %s %s | filial=%s usuario=%s tipo=RequestValidationError "
        "detail=%s",
        request.method,
        request.url.path,
        filial,
        usuario,
        detalhes,
    )
    return JSONResponse(status_code=422, content={"detail": detalhes})


@app.exception_handler(Exception)
async def _erro_nao_tratado(request: Request, exc: Exception) -> JSONResponse:
    """Envelope consistente; traceback sanitizado vai para o log."""
    filial, usuario = _contexto_auditoria()
    logger.exception(
        "HTTP 500 %s %s | filial=%s usuario=%s tipo=%s erro=%s",
        request.method,
        request.url.path,
        filial,
        usuario,
        type(exc).__name__,
        sanitizar(str(exc)),
        exc_info=(type(exc), exc, exc.__traceback__) if exc.__traceback__ else None,
    )
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
        filial, usuario = _contexto_auditoria()
        logger.warning(
            "HTTP 423 %s %s | filial=%s usuario=%s motivo=modo_leitura "
            "estado=%s detail=%s",
            request.method,
            request.url.path,
            filial,
            usuario,
            licensa_service.ESTADO.get("modo_leitura"),
            sanitizar(_MSG_MODO_LEITURA),
        )
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
