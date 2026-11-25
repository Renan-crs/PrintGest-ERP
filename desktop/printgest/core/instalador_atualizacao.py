"""Download validado e disparo do instalador (Fase 2, sem code signing).

O instalador é lançado em processo **destacado**: o `PrepareToInstall` do
`PrintGest.iss` encerra `PrintGest.exe` e `PrintGestAPI.exe`, então o processo
que disparou a atualização não pode ser o desktop. Após a instalação silenciosa,
a própria `[Run]` do instalador reabre o aplicativo (sem `skipifsilent`).

O instalador não é assinado nesta fase: o Windows SmartScreen pode exibir um
aviso. Isso é informado ao usuário antes do download e não pode ser suppressado
aqui — a única forma correta é adquirir certificado de code signing.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
from pathlib import Path

import httpx

_HOST_GITHUB = "github.com"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TAMANHO_MAX = 200 * 1024 * 1024

logger = logging.getLogger("printgest.desktop")


class ErroAtualizacao(RuntimeError):
    """Falha de download ou validação do instalador."""


def diretorio_downloads() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "PrintGest" / "updates"


def _sha256(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _validar(info: dict) -> tuple[str, str, str]:
    arquivo = str(info.get("arquivo") or "")
    if (
        not arquivo.lower().endswith(".exe")
        or "/" in arquivo
        or "\\" in arquivo
        or arquivo.startswith(".")
    ):
        raise ErroAtualizacao("Nome de instalador inválido no manifesto.")
    url = str(info.get("download_url") or "")
    try:
        if httpx.URL(url).host.lower() != _HOST_GITHUB:
            raise ErroAtualizacao("URL de download fora do GitHub.")
    except ErroAtualizacao:
        raise
    except Exception as exc:
        raise ErroAtualizacao("URL de download inválida.") from exc
    esperado = str(info.get("sha256") or "").lower()
    if not _SHA256.fullmatch(esperado):
        raise ErroAtualizacao("Hash SHA-256 inválido no manifesto.")
    return arquivo, url, esperado


def baixar_instalador(
    info: dict, cliente: httpx.Client | None = None
) -> Path:
    """Baixa o instalador e devolve o caminho somente se o SHA-256 conferir."""
    arquivo, url, esperado = _validar(info)
    destino = diretorio_downloads() / arquivo
    if destino.exists() and _sha256(destino) == esperado:
        logger.info("Instalador já baixado e validado: %s", arquivo)
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".download")
    pertence_ao_chamador = cliente is None
    cliente = cliente or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        with cliente.stream("GET", url) as resposta:
            if resposta.status_code != 200:
                raise ErroAtualizacao(
                    f"Download falhou (HTTP {resposta.status_code})."
                )
            tamanho = 0
            with temporario.open("wb") as saida:
                for bloco in resposta.iter_bytes(chunk_size=1024 * 1024):
                    tamanho += len(bloco)
                    if tamanho > _TAMANHO_MAX:
                        raise ErroAtualizacao("Instalador excede o tamanho permitido.")
                    saida.write(bloco)
    except httpx.HTTPError as exc:
        temporario.unlink(missing_ok=True)
        raise ErroAtualizacao("Falha de rede ao baixar o instalador.") from exc
    except ErroAtualizacao:
        temporario.unlink(missing_ok=True)
        raise
    finally:
        if pertence_ao_chamador:
            cliente.close()

    if _sha256(temporario) != esperado:
        temporario.unlink(missing_ok=True)
        raise ErroAtualizacao(
            "O arquivo baixado não confere com o SHA-256 da release. "
            "Nada foi executado."
        )
    temporario.replace(destino)
    logger.info("Instalador validado: %s (%s bytes)", arquivo, destino.stat().st_size)
    return destino


def iniciar_instalador(caminho: Path) -> int:
    """Dispara o Setup em processo destacado e devolve o PID."""
    if not caminho.is_file() or caminho.suffix.lower() != ".exe":
        raise ErroAtualizacao("Instalador não encontrado.")
    flags = 0
    for nome in (
        "CREATE_NO_WINDOW",
        "DETACHED_PROCESS",
        "CREATE_NEW_PROCESS_GROUP",
    ):
        flags |= getattr(subprocess, nome, 0)
    processo = subprocess.Popen(
        [str(caminho), "/VERYSILENT", "/NORESTART"],
        creationflags=flags,
        close_fds=True,
        cwd=str(caminho.parent),
    )
    logger.info("Instalador iniciado (pid=%s): %s", processo.pid, caminho.name)
    return processo.pid
