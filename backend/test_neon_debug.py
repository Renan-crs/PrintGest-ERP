#!/usr/bin/env python
"""Script de teste de conexão Neon Database"""
import sys
import os

# Carregar .env (usar o .env da raiz do backend)
from pathlib import Path
backend_dir = Path(__file__).parent
dotenv_path = backend_dir / '.env'

if dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path)
    
# Configurar logging debug
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Testar conexão com Neon
from sqlalchemy import create_engine, text

db_url = os.getenv('DATABASE_URL') or os.getenv('PRINTGEST_DATABASE_URL')
if not db_url:
    logger.error('DATABASE_URL nao configurada')
    sys.exit(1)

logger.info('Testing Neon Database connection...')

# Usar pooler para melhor performance
if 'pooler' not in db_url and '@' in db_url:
    # Adicionar pooler se não estiver usando pooler
    parts = db_url.split('@')
    if len(parts) == 2:
        db_url = parts[0] + '@' + parts[1].replace('.c-', '.c-').split('.')[0] + '-pooler.' + '.'.join(parts[1].split('.')[1:])

engine = create_engine(db_url, echo=False)

try:
    with engine.connect() as conn:
        result = conn.execute(text('SELECT 1 as test'))
        row = result.fetchone()
        logger.info('Conexao com Neon: SUCESSO')
        
        # Verificar tabelas
        result = conn.execute(text('''
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        '''))
        tables = [row[0] for row in result]
        logger.info(f'Tabelas: {len(tables)} encontradas')
        
        for table in tables[:5]:  # Mostrar primeiras 5 tabelas
            result = conn.execute(text(f'''
                SELECT COUNT(*) as count 
                FROM {table}
            '''))
            count = result.fetchone()[0]
            logger.info(f'  - {table}: {count} registros')
            
        if len(tables) > 5:
            logger.info(f'  ... e mais {len(tables) - 5} tabelas')
            
except Exception as e:
    logger.error(f'ERRO de conexao: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

logger.info('Teste de conexao concluido com sucesso!')