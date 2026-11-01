"""Garante o Local API Service no ar na instalação empacotada.

Em dev o backend é subido à mão (`run_dev.py`) e o desktop apenas conversa com
`127.0.0.1:8000`. Na instalação não existe "terminal" — o próprio desktop
verifica o `/health` e, quando o daemon não responde, sobe o
`PrintGestAPI.exe` instalado ao lado (layout do instalador:

    {app}\\PrintGest\\PrintGest.exe          <- este executável
    {app}\\PrintGestAPI\\PrintGestAPI.exe    <- daemon (Local API Service)
    {app}\\postgres\\pgsql\\bin              <- PostgreSQL embarcado

O exe do daemon cuida do resto: initdb/createdb/pg_ctl na primeira execução,
migrations Alembic e o uvicorn em 127.0.0.1:8000. O módulo é deliberadamente
sem Qt (testável puro); o `main.py` desenha o diálogo de espera.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

SAUDE_URL = "http://127.0.0.1:8000/health"
TEMPO_LIMITE_SUBIDA_SEGUNDOS = 90.0


def saude(timeout: float = 1.0) -> bool:
    """True quando o Local API Service responde ao /health."""
    try:
        httpx.get(SAUDE_URL, timeout=timeout)
        return True
    except (httpx.HTTPError, PermissionError, OSError):
        return False


def caminho_do_backend() -> Path | None:
    """`PrintGestAPI.exe` da instalação; None em dev (não empacotado)."""
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
    """Lança o daemon desanexado, sem janela de console e sem pipe aberto."""
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
    """Sobe o daemon quando necessário; True quando o /health responde.

    `a_cada_iteracao` é chamado a cada volta do laço de espera (o `main.py`
    passa `QApplication.processEvents` para manter o diálogo vivo).
    """
    if saude():
        return True
    caminho = caminho_do_backend()
    if caminho is None:
        # Não empacotado (dev): nada para subir — o roteador trata o daemon
        # ausente com o diálogo padrão "Local API Service indisponível".
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
