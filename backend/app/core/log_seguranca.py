"""Sanitização centralizada de texto e registros de log.

Nenhum erro deve ser registrado com token, senha, URL de banco com credenciais
ou chave de licença em claro. Este módulo é a fonte única das máscaras
(reutilizada por `fiscal_service` e por todos os handlers de erro).
"""

from __future__ import annotations

import logging
import re
import traceback
from contextvars import ContextVar
from typing import Any

request_id: ContextVar[str] = ContextVar("request_id", default="-")

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


class FiltroRequestId(logging.Filter):
    """Injeta o `request_id` da requisição corrente no registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True

_CHAVES_SENSIVEIS = (
    "token", "api_key", "apikey", "senha", "password", "authorization",
    "secret", "client_secret", "chave_privada", "private_key",
    "credencial", "certificado", "database_url", "redgest_url",
    "fiscal_gateway_token", "chave_ativacao", "codigo_licenca",
)

_PADROES_SEGREDOS = (
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
    re.compile(
        r"(postgresql(?:\+psycopg)?://)[^:@/\s]+:[^@/\s]+@", re.IGNORECASE
    ),
    re.compile(
        r"\b(token|api[_-]?key|apikey|senha|password|secret|authorization"
        r"|chave[_-]?privada|private[_-]?key|credencial|certificado"
        r"|client_secret|chave_ativacao|codigo_licenca|fiscal_gateway_token)"
        r"\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\b"),
    re.compile(r"\b(sk_|rk_)[A-Za-z0-9_\-]+", re.IGNORECASE),
)


def mascarar_texto(valor: str) -> str:
    """Mascara credenciais em mensagens livres antes de gravar em log/auditoria."""
    texto = str(valor)
    for padrao in _PADROES_SEGREDOS:
        texto = padrao.sub(_substituir, texto)
    return texto


def _substituir(match: re.Match[str]) -> str:
    try:
        grupo = match.group(1)
    except IndexError:
        grupo = None
    if grupo is None:
        return "***"
    return f"{grupo}***"


def sanitizar(valor: Any) -> Any:
    """Versão recursiva para dicts/listas (ex.: `exc.detail` do FastAPI)."""
    if isinstance(valor, dict):
        return {
            chave: (
                "***"
                if any(s in str(chave).lower() for s in _CHAVES_SENSIVEIS)
                else sanitizar(item)
            )
            for chave, item in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [sanitizar(item) for item in valor]
    if isinstance(valor, str):
        return mascarar_texto(valor)
    return valor


class FiltroSeguranca(logging.Filter):
    """Aplica `sanitizar` a todo registro, inclusive ao traceback formatado."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mascarar_texto(record.msg)
        if isinstance(record.args, dict):
            record.args = sanitizar(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(sanitizar(arg) for arg in record.args)
        if record.exc_info and not record.exc_text:
            texto = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = mascarar_texto(texto)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = mascarar_texto(record.exc_text)
        return True
