#!/usr/bin/env python
"""Entry point do Local API Service para o executável empacotado (PyInstaller).

Diferente do `run_dev.py` (desenvolvimento, com reload), este arquivo prepara o
ambiente da instalação antes de servir:

1. Carrega o `.env` ao lado do **executável** no `os.environ` — o pydantic
   resolve `env_file=".env"` pelo CWD, e o CWD de um atalho do menu Iniciar não
   é garantido. Variáveis de ambiente reais continuam vencendo o arquivo.
2. Usa Neon Database (PostgreSQL gerenciado em nuvem) quando
   `PRINTGEST_PG_EMBARCADO=false` - não há PostgreSQL embarcado desde v0.3.5.
3. Registra log em arquivo (`logs/printgest-api.log` ao lado do exe) quando
   congelado — sem console, o log em arquivo é o único rastro de diagnóstico.
4. Serve o app via uvicorn (sem reload), no host/porta das configurações.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _carregar_env_do_executavel() -> None:
    """Injeta o `.env` ao lado do exe no ambiente (só chaves ainda não definidas)."""
    if not getattr(sys, "frozen", False):
        return
    ini = Path(sys.executable).resolve().parent / ".env"
    if not ini.exists():
        return
    for linha in ini.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        os.environ.setdefault(chave.strip(), valor.strip())


def _garantir_streams() -> None:
    """Evita `sys.stderr=None` em binário windowed (PyInstaller console=False)."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _anexar_log_em_arquivo() -> None:
    """Copia os logs para `logs/printgest-api.log` (rotativo, até 5 MB × 3).

    Chamado ANTES de `basicConfig()` e de `import app.main`: com o FileHandler
    já instalado, nenhum StreamHandler aponta para um `stderr` inexistente —
    é o pré-requisito para trocar o spec do daemon para `console=False`.
    """
    from app.core.log_seguranca import (
        FiltroRequestId,
        FiltroSeguranca,
        _LOG_FORMAT,
    )

    if not getattr(sys, "frozen", False):
        return
    try:
        pasta = Path(sys.executable).resolve().parent / "logs"
        pasta.mkdir(exist_ok=True)
        manipulador = RotatingFileHandler(
            pasta / "printgest-api.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        manipulador.setFormatter(logging.Formatter(_LOG_FORMAT))
        manipulador.addFilter(FiltroRequestId())
        manipulador.addFilter(FiltroSeguranca())
        logging.getLogger().addHandler(manipulador)
    except OSError:
        pass  # disco cheio/permissão: o serviço segue — log é best-effort


def _log_configuracao_inicial() -> None:
    """Log da configuração de inicialização para diagnóstico."""
    logger = logging.getLogger("printgest")
    logger.info(
        "=== PrintGest API Service v%s ===",
        logging.getLogger("app.core.config")
        .__dict__.get("settings", {})
        .get("version", "unknown"),
    )
    logger.info(
        "Modo: %s",
        "Neon Database"
        if not getattr(sys, "frozen", False)
        or __import__("os").environ.get("PRINTGEST_PG_EMBARCADO", "false").lower()
        != "true"
        else "PostgreSQL embarcado",
    )
    logger.info(
        "Banco de dados: %s", "Neon Cloud" if getattr(sys, "frozen", False) else "Local"
    )


def main() -> None:
    _carregar_env_do_executavel()
    _garantir_streams()

    # Log em arquivo PRIMEIRO: basicConfig() não acrescenta StreamHandler
    # quando a raiz já tem handler, e `import app.main` respeita isso.
    _anexar_log_em_arquivo()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("printgest")
    logger.info("PrintGest API Service inicializando...")

    import uvicorn

    from app.core.config import settings

    if settings.pg_embarcado:
        logger.info("Iniciando PostgreSQL embarcado...")
        from app.core.postgres_embarcado import garantir_postgres

        garantir_postgres()
    else:
        logger.info("Usando Neon Database (PostgreSQL gerenciado em nuvem)")

    # Verificar variáveis críticas
    logger.info(
        "DATABASE_URL configurada: %s", "SIM" if settings.database_url else "NAO"
    )
    logger.info("REDGEST_URL: %s", settings.redgest_url)
    logger.info("ENV: %s", settings.env)

    # O app herda o handler de arquivo instalado acima (sem stderr).
    from app.main import app

    logger.info("Iniciando uvicorn em %s:%s", settings.api_host, settings.api_port)
    # `log_config=None`: não deixa o uvicorn substituir os handlers de arquivo
    # instalados por `_anexar_log_em_arquivo()` (nem apontá-los para o DEVNULL).
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
