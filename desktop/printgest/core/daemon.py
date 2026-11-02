"""Garante o Local API Service no ar na instalacao empacotada.

Em dev o backend é subido à mão (`run_dev.py`) e o desktop apenas conversa com
`127.0.0.1:8000`. Na instalacao não existe "terminal" — o próprio desktop
verifica o `/health` e, quando o daemon não responde, sobe o
`PrintGestAPI.exe` instalado ao lado (layout do instalador:

    {app}\PrintGest\PrintGest.exe          <- este executavel
    {app}\PrintGestAPI\PrintGestAPI.exe    <- daemon (Local API Service)

O exe do daemon cuida do resto: migrations Alembic e o uvicorn em 127.0.0.1:8000.
O modulo é deliberadamente sem Qt (testavel puro); o `main.py` desenha o dialogo de espera.

NOTA: A partir da v0.3.5, o sistema usa Neon como banco de dados gerenciado.
PostgreSQL embarcado foi removido do instalador.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

SAUDE_URL = "http://127.0.0.1:8000/health"
TEMPO_LIMITE_SUBIDA_SEGUNDOS = 120.0  # Aumentado de 90s para 2min (Neon cold start)


def saude(timeout: float = 1.0) -> bool:
    """True quando o Local API Service responde ao /health.
    
    Tenta conexao HTTP primeiro, mas se falhar por permissões SSL,
    verifica se a porta esta aberta como fallback.
    """
    import httpx
    import logging
    logger = logging.getLogger("printgest.daemon")
    
    # Primeiro tenta HTTP com httpx
    try:
        resp = httpx.get(SAUDE_URL, timeout=timeout)
        if resp.status_code == 200:
            return True
        logger.debug("Health check retornou status %s", resp.status_code)
        return False
    except PermissionError:
        # Erro de permissao SSL - verificar se porta esta aberta
        logger.debug("PermissionError ao acessar health endpoint")
        return _porta_aberta(timeout)
    except OSError as e:
        logger.debug("OSError ao acessar health endpoint: %s", e)
        return _porta_aberta(timeout)
    except httpx.HTTPError as e:
        # Conexao recusada ou timeout - verificar porta como fallback
        logger.debug("HTTPError ao acessar health endpoint: %s", e)
        return _porta_aberta(timeout)


def _porta_aberta(timeout: float = 1.0) -> bool:
    """Verifica se a porta 8000 esta aberta (sem usar HTTP)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        return result == 0
    except (OSError, socket.error):
        return False


def caminho_do_backend() -> Path | None:
    """`PrintGestAPI.exe` da instalacao; None em dev (nao empacotado)."""
    explicito = os.environ.get("PRINTGEST_API_EXE", "").strip()
    if explicito:
        caminho = Path(explicito)
        return caminho if caminho.exists() else None
    if getattr(sys, "frozen", False):
        irma = Path(sys.executable).resolve().parent.parent
        candidato = irma / "PrintGestAPI" / "PrintGestAPI.exe"
        return candidato if candidato.exists() else None
    return None


def subir(caminho: Path) -> None:
    """Lanca o daemon desanexado, sem janela de console e sem pipe aberto."""
    subprocess.Popen(
        [str(caminho)],
        cwd=str(caminho.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def garantir(
    segundos: float = TEMPO_LIMITE_SUBIDA_SEGUNDOS, a_cada_iteracao=None
) -> bool:
    """Sobe o daemon quando necessario; True quando o /health responde.
    
    `a_cada_iteracao` e chamado a cada volta do laço de espera (o `main.py`
    passa `QApplication.processEvents` para manter o dialogo vivo).
    """
    import logging
    logger = logging.getLogger("printgest.daemon")
    
    if saude():
        return True
    caminho = caminho_do_backend()
    if caminho is None:
        # Nao empacotado (dev): nada para subir — o roteador trata o daemon
        # ausente com o dialogo padrao "Local API Service indisponivel".
        logger.debug("Daemon nao empacotado - nada para subir")
        return saude(timeout=3.0)
    
    logger.info("Subindo PrintGestAPI.exe de %s", caminho)
    subir(caminho)
    limite = time.monotonic() + segundos
    tentativas = 0
    while time.monotonic() < limite:
        if a_cada_iteracao is not None:
            a_cada_iteracao()
        if saude(timeout=1.0):
            elapsed = time.monotonic() - (limite - segundos)
            logger.info("Daemon pronto apos %.1f segundos", elapsed)
            return True
        tentativas += 1
        if tentativas % 4 == 0:  # Log a cada 1 segundo
            elapsed = time.monotonic() - (limite - segundos)
            logger.debug("Aguardando daemon... %.0fs de %ds", elapsed, int(segundos))
        time.sleep(0.25)
    logger.warning("Timeout (%ds) aguardando daemon", int(segundos))
    return False