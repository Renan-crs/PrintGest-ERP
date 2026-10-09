"""Aplicação de migrations Alembic no startup do serviço.

Motivação: o Local API Service não garantia que o banco estivesse na revisão
esperada pelo código. Um banco atrás do `head` gera 500s em runtime (ex.:
`coluna funcionario.observacoes não existe`) mesmo com a suíte verde — os testes
recriam e migram o banco dedicado a cada execução. Aqui rodamos
`alembic upgrade head` de forma idempotente no início do lifespan.

Controlado por `PRINTGEST_AUTO_MIGRATE` (default `True`). A suíte desliga a
chave no `conftest.py` para nunca tocar no banco de desenvolvimento.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("printgest")

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def aplicar_migrations() -> None:
    """Roda `alembic upgrade head` (idempotente) contra `settings.database_url`.

    Executado como subprocesso para isolar a configuração de logging do Alembic
    (o `env.py` chama `fileConfig`, que reconfiguraria o logger da aplicação).
    Em caso de falha o startup é abortado — melhor falhar cedo e alto do que
    servir 500s por drift de schema.
    """
    if not settings.auto_migrate:
        return

    env = {**os.environ, "PRINTGEST_DATABASE_URL": settings.database_url}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "Falha ao aplicar migrations no startup "
            "(alembic upgrade head):\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )
    logger.info("Migrations Alembic verificadas (upgrade head).")
