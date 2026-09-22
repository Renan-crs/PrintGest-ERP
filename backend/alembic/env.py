import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

print("ENV: inicio", flush=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("ENV: a importar app.models", flush=True)
import app.models  # noqa: F401  — registra todas as tabelas no metadata
print("ENV: app.models importado", flush=True)
from app.core.config import settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    print("ENV: create engine", flush=True)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    print("ENV: conectar", flush=True)
    with connectable.connect() as connection:
        print("ENV: conectado, configurar alembic", flush=True)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            print("ENV: run_migrations", flush=True)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()