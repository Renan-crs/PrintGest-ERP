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

# No exe congelado (PyInstaller onedir) os dados carregados por `datas` ficam
# em `sys._MEIPASS` (pasta `_internal` do bundle): `alembic.ini` e `alembic/`.
# Em dev continua sendo a raiz do backend (o subprocesso roda a partir dali).
if getattr(sys, "frozen", False):
    _BACKEND_DIR = Path(getattr(sys, "_MEIPASS", "."))
else:
    _BACKEND_DIR = Path(__file__).resolve().parents[2]


def _upgrade_congelado() -> None:
    """`alembic upgrade head` pela API Python (exe congelado não tem `python -m`).

    O `Config` é montado sem arquivo: `alembic/env.py` só chama `fileConfig`
    quando `config.config_file_name` existe — sem ini, o logging da aplicação
    (root + request_id) não é reconfigurado pelo Alembic no processo vivo.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:
        # Caso clássico em Neon: o banco foi criado pelo papel dono
        # (`neondb_owner`) e a instalação usa um papel sem posse das tabelas.
        # O stack trace do Alembic não diz o que fazer; traduzimos.
        if _erro_de_permissao(exc):
            raise RuntimeError(
                "Sem permissão para aplicar migrations no banco. O usuário de "
                "PRINTGEST_DATABASE_URL precisa ser dono das tabelas do schema "
                "public (ou membro do papel dono). Peça ao suporte para ajustar "
                "o papel do banco antes de abrir o PrintGest.\n"
                f"{exc}"
            ) from exc
        raise


def _erro_de_permissao(exc: BaseException) -> bool:
    """`True` quando a falha do Alembic é de privilégio (não de schema)."""
    texto = f"{type(exc).__name__}: {exc}".lower()
    marcas = (
        "insufficientprivilege",
        "must be owner",
        "permission denied for schema",
        "permission denied for table",
        "permission denied for relation",
    )
    return any(marca in texto for marca in marcas)


def aplicar_migrations() -> None:
    """Roda `alembic upgrade head` (idempotente) contra `settings.database_url`.

    Executado como subprocesso para isolar a configuração de logging do Alembic
    (o `env.py` chama `fileConfig`, que reconfiguraria o logger da aplicação).
    Em caso de falha o startup é abortado — melhor falhar cedo e alto do que
    servir 500s por drift de schema.

    No executável empacotado não há interpretador para o subprocesso — a mesma
    atualização roda pela API Python do Alembic, no processo.
    """
    if not settings.auto_migrate:
        return

    if getattr(sys, "frozen", False):
        _upgrade_congelado()
        logger.info("Migrations Alembic verificadas (upgrade head).")
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
