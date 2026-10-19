"""Cofre do SO para segredos locais (doc de integração RedGest §9.4).

A doc exige que a **chave de ativação** fique em cofre do sistema operacional
(Windows: DPAPI / macOS: Keychain / Linux: Secret Service) e não em texto puro
no banco. Aqui a chave é guardada **cifrada com DPAPI em escopo de máquina**
(`CRYPTPROTECT_LOCAL_MACHINE`): qualquer processo daquele computador consegue
ler, mas o valor é inútil fora dele — isso protege backup/dump do banco sem
exigir uma segunda credencial nem amarrar o segredo ao perfil do usuário que
ativou (o Local API Service pode rodar como serviço, com outra conta).

- `proteger(texto)` → `"dpapi:v1:<base64>"`.
- `revelar(valor)` → volta ao texto; valores **sem** o prefixo (linhas gravadas
  antes do cofre) são devolvidos como estão; blob ilegível (banco copiado para
  outra máquina) devolve `""`, o que força nova ativação em vez de enviar lixo
  ao RedGest.

Fora do Windows o DPAPI não existe: `proteger` grava em texto puro e registra um
aviso (o Local API Service só roda em Windows em produção). `PRINTGEST_COFRE=nenhum`
desliga o cofre explicitamente.
"""

from __future__ import annotations

import base64
import ctypes
import logging
import platform

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIXO = "dpapi:v1:"
# CRYPTPROTECT_LOCAL_MACHINE: o blob vale para a máquina, não para o usuário.
_ESCOPO_MAQUINA = 0x04
_DESCRICAO = "printgest-licenca"


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _cript32():
    """Carrega `crypt32` (só Windows); `None` quando indisponível."""
    if platform.system() != "Windows":
        return None
    try:
        return ctypes.WinDLL("crypt32", use_last_error=True)
    except (OSError, AttributeError):  # pragma: no cover - Windows sem crypt32
        logger.warning("crypt32 indisponível: cofre do SO desligado.")
        return None


def disponivel() -> bool:
    """`True` quando o cofre do SO está configurado e existe nesta máquina."""
    return (settings.cofre or "").lower() == "dpapi" and _cript32() is not None


def _executar(dados: bytes, *, proteger_dados: bool) -> bytes | None:
    """Chama CryptProtectData/CryptUnprotectData; `None` em falha."""
    lib = _cript32()
    if lib is None:
        return None
    origem = ctypes.create_string_buffer(dados, len(dados))
    entrada = _Blob(len(dados), ctypes.cast(origem, ctypes.POINTER(ctypes.c_ubyte)))
    saida = _Blob()
    if proteger_dados:
        ok = lib.CryptProtectData(
            ctypes.byref(entrada),
            _DESCRICAO,
            None,
            None,
            None,
            _ESCOPO_MAQUINA,
            ctypes.byref(saida),
        )
    else:
        ok = lib.CryptUnprotectData(
            ctypes.byref(entrada),
            None,
            None,
            None,
            None,
            _ESCOPO_MAQUINA,
            ctypes.byref(saida),
        )
    if not ok:
        logger.warning(
            "DPAPI falhou ao %s o segredo da licença (erro %s).",
            "proteger" if proteger_dados else "revelar",
            ctypes.get_last_error(),
        )
        return None
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(saida.pbData)


def proteger(texto: str) -> str:
    """Guarda o segredo no cofre; devolve o valor pronto para o banco."""
    if not texto:
        return ""
    if not disponivel():
        if (settings.cofre or "").lower() == "dpapi":
            logger.warning(
                "Cofre do SO indisponível: a chave da licença será gravada em texto puro."
            )
        return texto
    cifrado = _executar(texto.encode("utf-8"), proteger_dados=True)
    if not cifrado:
        return texto
    return PREFIXO + base64.b64encode(cifrado).decode("ascii")


def revelar(valor: str | None) -> str:
    """Devolve o segredo em claro; `""` quando o blob é ilegível nesta máquina."""
    if not valor:
        return ""
    if not valor.startswith(PREFIXO):
        # Linha gravada antes do cofre (ou cofre desligado): já é texto puro.
        return valor
    if _cript32() is None:
        return ""
    try:
        cifrado = base64.b64decode(valor[len(PREFIXO) :], validate=True)
    except (ValueError, TypeError):
        logger.warning("Chave de licença no cofre está corrompida.")
        return ""
    claro = _executar(cifrado, proteger_dados=False)
    if not claro:
        logger.warning(
            "Não foi possível abrir a chave de licença no cofre (banco de outra máquina?)."
        )
        return ""
    return claro.decode("utf-8", errors="replace")
