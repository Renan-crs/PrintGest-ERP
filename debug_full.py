#!/usr/bin/env python
"""Script de inicialização em modo depuração para PrintGest ERP v0.3.8"""
import sys
import os
import logging

# Carregar .env do backend
from pathlib import Path
backend_dir = Path(__file__).parent / 'backend'
dotenv_path = backend_dir / '.env'

if dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path)

# Configurar logging VERBOSE
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

logger = logging.getLogger("debug")
logger.info("=" * 70)
logger.info("INICIALIZAÇÃO DEBUG - PrintGest ERP v0.3.8")
logger.info("=" * 70)

try:
    # 1. Testar configuração
    logger.info("\n[1] Carregando configurações...")
    sys.path.insert(0, str(backend_dir))
    from app.core.config import settings
    logger.info(f"Database URL: {settings.database_url[:50]}...")
    logger.info(f"Session TTL: {settings.session_ttl_minutes} minutos")
    logger.info(f"Auto-migrate: {settings.auto_migrate}")
    
    # 2. Testar conexão com Neon
    logger.info("\n[2] Testando conexão com Neon Database...")
    from sqlalchemy import create_engine, text
    
    engine = create_engine(settings.database_url, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1 as test'))
        logger.info("Conexão Neon: SUCESSO")
        
        # Contar tabelas
        result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
        count = result.scalar()
        logger.info(f"Tabelas no banco: {count}")
        
        # Verificar migrations
        result = conn.execute(text("SELECT DISTINCT version_num FROM alembic_version"))
        revisions = [row[0] for row in result]
        logger.info(f"Migrations: {revisions}")
    
    # 3. Testar modelo
    logger.info("\n[3] Testando modelos SQLAlchemy...")
    from app.db import Base, engine
    from app import models  # Importar todos os modelos
    
    # Configurar mappers
    from sqlalchemy.orm import configure_mappers
    configure_mappers()
    logger.info("Modelos configurados com sucesso")
    
    # 4. Verificar sessões
    logger.info("\n[4] Verificando sessões de usuário...")
    from app.models.core import Usuario, UsuarioSessao
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM usuario_sessao"))
        sessoes = result.scalar()
        logger.info(f"Sessões ativas: {sessoes}")
    
    logger.info("\n" + "=" * 70)
    logger.info("STATUS: TUDO FUNCIONANDO PERFEITAMENTE!")
    logger.info("=" * 70)
    
except Exception as e:
    logger.error(f"ERRO: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)