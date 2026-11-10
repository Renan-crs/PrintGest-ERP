import logging
import threading

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# ------------------------------------------------------------- keep-alive
# Neon suspende o compute (scale-to-zero) após ~5 min sem atividade e encerra as
# conexões abertas. O efeito na produção era: após alguns minutos parado, a
# primeira ação do usuário esperava o *cold start* (ou falhava na conexão morta
# do pool) — "sistema lento ao salvar" e a impressão de sessão perdida. O ping
# periódico mantém o compute acordado e o pool saudável enquanto o daemon roda.
_keepalive_timer: threading.Timer | None = None
_keepalive_lock = threading.Lock()


def _ping() -> None:
    global _keepalive_timer
    with _keepalive_lock:
        _keepalive_timer = None
    intervalo = settings.db_keepalive_segundos
    if intervalo <= 0:
        return
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:  # noqa: BLE001 — keep-alive nunca derruba o serviço
        logger.warning(
            "Keep-alive do banco falhou — o banco acorda normalmente na "
            "próxima requisição."
        )
    _armar(intervalo)


def _armar(intervalo: int) -> None:
    global _keepalive_timer
    with _keepalive_lock:
        if _keepalive_timer is not None:
            return
        timer = threading.Timer(intervalo, _ping)
        timer.daemon = True
        _keepalive_timer = timer
    timer.start()


def iniciar_keepalive() -> None:
    """Inicia o ping periódico de banco (`PRINTGEST_DB_KEEPALIVE_SEGUNDOS`).

    Idempotente: chamar de novo não duplica o timer. `0` desliga o mecanismo.
    O timer é daemon: morre junto com o processo, sem limpeza explícita.
    """
    intervalo = settings.db_keepalive_segundos
    if intervalo <= 0:
        logger.info("Keep-alive do banco desligado por configuração.")
        return
    _armar(intervalo)
