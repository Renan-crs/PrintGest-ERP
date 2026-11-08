#!/usr/bin/env python
"""Script de teste rápido do backend em modo depuração"""

import logging
import sys
from pathlib import Path

# Carregar .env do backend
backend_dir = Path(__file__).parent
dotenv_path = backend_dir / ".env"

if dotenv_path.exists():
    from dotenv import load_dotenv

    load_dotenv(dotenv_path)

# Configurar logging verbose
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger("debug")

print("=" * 70)
print("TESTE DE DEPURAÇÃO - PrintGest Backend v0.3.8")
print("=" * 70)

try:
    # Add backend to path
    sys.path.insert(0, str(backend_dir))

    # Testar configuração
    logger.info("Carregando configurações...")
    from app.core.config import settings

    logger.info(f"Database URL: {settings.database_url.split('@')[-1]}")
    logger.info(f"API Host: {settings.api_host}:{settings.api_port}")
    logger.info(f"ENV: {settings.env}")
    logger.info(f"Auto-migrate: {settings.auto_migrate}")

    # Testar conexão com Neon
    logger.info("Testando conexão com Neon Database...")
    from sqlalchemy import create_engine, text

    engine = create_engine(settings.database_url, echo=False)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1 as test"))
        logger.info("✅ Conexão com Neon: SUCESSO")

        # Contar tabelas
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        count = result.scalar()
        logger.info(f"📊 Tabelas no banco: {count}")

        # Verificar migrations status
        result = conn.execute(text("SELECT * FROM alembic_version"))
        for row in result:
            logger.info(f"Migration status: {row[0]}")

except Exception as e:  # noqa: BLE001 — script de diagnóstico: toda falha é reportada
    logger.error(f"❌ ERRO: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("=" * 70)
print("TESTE CONCLUÍDO COM SUCESSO!")
print("=" * 70)
print("\nPara iniciar o servidor:")
print("  .venv\\Scripts\\activate")
print("  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
