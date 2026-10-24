r"""PostgreSQL embarcado: prepara o cluster no primeiro uso da instalação.

O instalador entrega os binários do PostgreSQL em `<raiz>\pgsql` e este módulo
deixa o banco pronto para o Local API Service — o usuário final não configura
nada de banco (PRD §5: instalação única, sem configuração manual). A sequência
é idempotente e roda no início do `run_server.py` (exe congelado):

1. `initdb` quando `<raiz>\data` não tem `PG_VERSION` — superusuário, locale e
   encoding iguais ao `scripts/setup_postgres.ps1` usado em dev
   (locale C, UTF8, `-A trust`, escuta só em 127.0.0.1).
2. `pg_ctl start` se o cluster não estiver no ar (porta e endereço vindos do
   `database_url`; log em `<raiz>\postgres.log`).
3. Espera `pg_isready` aceitar conexões (subida a frio pode levar segundos).
4. `CREATE DATABASE` do banco da URL quando ainda não existir.

Ativado por `PRINTGEST_PG_EMBARCADO=true` (o `.env` gerado pelo instalador
carrega a chave); em desenvolvimento o flag fica desligado e nada roda.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.core.config import settings

logger = logging.getLogger("printgest")

TEMPO_LIMITE_SUBIDA_SEGUNDOS = 60
_NOME_BANCO_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _partes_url() -> tuple[str, int, str, str]:
    """(host, porta, usuário, banco) do `database_url` — fonte única da verdade.

    O cluster embarcado atende apenas a interface de loopback; uma URL
    apontando para outro host é erro de configuração, não algo para "corrigir".
    """
    u = urlsplit(settings.database_url)
    if u.scheme.split("+")[0] != "postgresql":
        raise RuntimeError(
            f"PRINTGEST_DATABASE_URL inesperado para o PostgreSQL embarcado: "
            f"{settings.database_url!r}"
        )
    host = u.hostname or ""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "O PostgreSQL embarcado só atende 127.0.0.1 — ajuste o "
            "PRINTGEST_DATABASE_URL da instalação."
        )
    usuario = unquote(u.username or "printgest")
    banco = (u.path or "").lstrip("/") or "printgest"
    if not _NOME_BANCO_VALIDO.match(banco):
        raise RuntimeError(f"Nome de banco inválido no PRINTGEST_DATABASE_URL: {banco!r}")
    return host, u.port or 5432, usuario, banco


def raiz_do_postgres() -> Path:
    """Onde vivem `pgsql\bin` e `data` do PostgreSQL embarcado."""
    if settings.pg_raiz.strip():
        return Path(settings.pg_raiz.strip())
    if getattr(sys, "frozen", False):
        # Layout do instalador: {app}\PrintGestAPI\PrintGestAPI.exe e
        # {app}\postgres\pgsql\bin — a raiz é irmã da pasta do executável.
        return Path(sys.executable).resolve().parent / "postgres"
    return Path(__file__).resolve().parents[3] / ".dev" / "postgres"


def _rodar(comando: list[str], etapa: str) -> str:
    """Executa uma ferramenta do PostgreSQL; devolve a saída ou explode alto."""
    resultado = subprocess.run(
        [str(c) for c in comando],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if resultado.returncode != 0:
        detalhe = (resultado.stdout or "") + (resultado.stderr or "")
        raise RuntimeError(
            f"Falha ao preparar o banco local ({etapa}).\n{detalhe.strip()[-2000:]}"
        )
    return resultado.stdout or ""


def _no_ar(bin_dir: Path, data_dir: Path) -> bool:
    resultado = subprocess.run(
        [str(bin_dir / "pg_ctl.exe"), "status", "-D", str(data_dir)],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return resultado.returncode == 0


def _inicializar(bin_dir: Path, data_dir: Path, usuario: str) -> None:
    logger.info("Primeira execução: inicializando o banco local (initdb)...")
    _rodar(
        [
            bin_dir / "initdb.exe",
            "-D",
            data_dir,
            "-U",
            usuario,
            "--locale=C",
            "--encoding=UTF8",
            "-A",
            "trust",
        ],
        "initdb",
    )


def _iniciar(
    bin_dir: Path, data_dir: Path, log: Path, host: str, porta: int
) -> None:
    logger.info("Iniciando o PostgreSQL embarcado em %s:%s...", host, porta)
    _rodar(
        [
            bin_dir / "pg_ctl.exe",
            "start",
            "-D",
            data_dir,
            "-l",
            log,
            "-o",
            f"-p {porta} -c listen_addresses={host}",
        ],
        "pg_ctl start",
    )


def _aguardar(bin_dir: Path, host: str, porta: int) -> None:
    pronto = False
    for _ in range(TEMPO_LIMITE_SUBIDA_SEGUNDOS * 2):
        resultado = subprocess.run(
            [
                str(bin_dir / "pg_isready.exe"),
                "-h",
                host,
                "-p",
                str(porta),
                "-q",
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if resultado.returncode == 0:
            pronto = True
            break
        time.sleep(0.5)
    if not pronto:
        raise RuntimeError(
            f"O banco local não respondeu em {host}:{porta} em até "
            f"{TEMPO_LIMITE_SUBIDA_SEGUNDOS} s."
        )


def _garantir_banco(
    bin_dir: Path, host: str, porta: int, usuario: str, banco: str
) -> None:
    psql = bin_dir / "psql.exe"
    existe = _rodar(
        [
            psql,
            "-h",
            host,
            "-p",
            str(porta),
            "-d",
            "postgres",
            "-U",
            usuario,
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = %s" % f"'{banco}'",
        ],
        "psql",
    ).strip()
    if existe != "1":
        logger.info("Criando o banco de dados '%s'...", banco)
        _rodar(
            [
                psql,
                "-h",
                host,
                "-p",
                str(porta),
                "-d",
                "postgres",
                "-U",
                usuario,
                "-c",
                f'CREATE DATABASE "{banco}" OWNER "{usuario}"',
            ],
            "CREATE DATABASE",
        )


def garantir_postgres() -> None:
    """Deixa o PostgreSQL embarcado no ar com o banco da URL criado."""
    raiz = raiz_do_postgres()
    bin_dir = raiz / "pgsql" / "bin"
    if not (bin_dir / "pg_ctl.exe").exists():
        raise RuntimeError(
            f"PostgreSQL embarcado não encontrado em {bin_dir}. "
            "Reinstale o PrintGest ERP."
        )
    data_dir = raiz / "data"
    log = raiz / "postgres.log"
    host, porta, usuario, banco = _partes_url()

    if not (data_dir / "PG_VERSION").exists():
        _inicializar(bin_dir, data_dir, usuario)
    if not _no_ar(bin_dir, data_dir):
        _iniciar(bin_dir, data_dir, log, host, porta)
    _aguardar(bin_dir, host, porta)
    _garantir_banco(bin_dir, host, porta, usuario, banco)
    logger.info("PostgreSQL embarcado pronto em %s:%s/%s.", host, porta, banco)
