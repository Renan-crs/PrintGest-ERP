"""Log rotativo do desktop — erros detalhados mesmo em binário `console=False`.

Sem imports de Qt: pode ser chamado antes do QApplication (captura falhas de
startup). Caminho padrão: `<exe>/logs/printgest.log` quando congelado, ou
`%LOCALAPPDATA%/PrintGest/logs/printgest.log` em desenvolvimento.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Mesmas chaves mascaradas pelo backend (`app/core/log_seguranca.py`), para que
# um erro do cliente nunca grave licença, DSN ou credencial de integração.
_PADROES = (
    re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(postgresql(?:\+psycopg)?://)[^:@/\s]+:[^@/\s]+@", re.IGNORECASE),
    re.compile(
        r"\b(token|api[_-]?key|apikey|senha|password|secret|authorization"
        r"|chave[_-]?privada|private[_-]?key|credencial|certificado"
        r"|client_secret|chave[_-]?ativacao|chave[_-]?licenca|codigo[_-]?licenca"
        r"|codigo[_-]?ativacao|product[_-]?key|database[_-]?url|redgest[_-]?url"
        r"|fiscal[_-]?gateway[_-]?token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\b[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\b"),
    re.compile(r"\b(sk_|rk_)[A-Za-z0-9_\-]+", re.IGNORECASE),
)


def _substituir(match: re.Match[str]) -> str:
    # Nem todos os padrões têm grupo 1 (ex.: chave de produto completa).
    try:
        grupo = match.group(1)
    except IndexError:
        grupo = None
    if grupo is None:
        return "***"
    return f"{grupo.rstrip()} ***"


def mascarar(valor: str) -> str:
    texto = str(valor)
    for padrao in _PADROES:
        texto = padrao.sub(_substituir, texto)
    return texto


class FiltroSeguranca(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mascarar(record.msg)
        if isinstance(record.args, dict):
            record.args = {
                k: mascarar(v) if isinstance(v, str) else v
                for k, v in record.args.items()
            }
        elif isinstance(record.args, tuple):
            # Preserva tipos não-str (%d/%f dos logs do httpx/uvicorn).
            record.args = tuple(
                mascarar(v) if isinstance(v, str) else v for v in record.args
            )
        if record.exc_info and not record.exc_text:
            record.exc_text = mascarar("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        if record.exc_text:
            record.exc_text = mascarar(record.exc_text)
        return True


def caminho_log() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PrintGest"
    return base / "logs" / "printgest.log"


def configurar_logging(caminho: Path | None = None) -> Path:
    """Configura o log do desktop; idempotente e best-effort."""
    destino = caminho or caminho_log()
    root = logging.getLogger()
    root.setLevel(os.environ.get("PRINTGEST_LOG_NIVEL", "INFO").upper())
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
    )
    if not any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", "").lower() == str(destino.resolve()).lower()
        for h in root.handlers
    ):
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                destino,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(fmt)
            handler.addFilter(FiltroSeguranca())
            root.addHandler(handler)
        except OSError:
            pass
    for handler in root.handlers:
        if not any(isinstance(f, FiltroSeguranca) for f in handler.filters):
            handler.addFilter(FiltroSeguranca())
    return destino
