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
TEMPO_LIMITE_SUBIDA_SEGUNDOS = 90.0


def saude(timeout: float = 1.0) -> bool:
    """True quando o Local API Service responde ao /health.
    
    Tenta conexao HTTP primeiro, mas se falhar por permissões SSL,
    verifica se a porta esta aberta como fallback.
    """
    import httpx
    
    # Primeiro tenta HTTP com httpx
    try:
        httpx.get(SAUDE_URL, timeout=timeout)
        return True
    except PermissionError:
        # Erro de permissao SSL - verificar se porta esta aberta
        return _porta_aberta(timeout)
    except OSError:
        return _porta_aberta(timeout)
    except httpx.HTTPError:
        # Conexao recusada ou timeout - verificar porta como fallback
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
    if saude():
        return True
    caminho = caminho_do_backend()
    if caminho is None:
        # Nao empacotado (dev): nada para subir — o roteador trata o daemon
        # ausente com o dialogo padrao "Local API Service indisponivel".
        return saude(timeout=3.0)
    subir(caminho)
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if a_cada_iteracao is not None:
            a_cada_iteracao()
        if saude(timeout=1.0):
            return True
        time.sleep(0.25)
    return False