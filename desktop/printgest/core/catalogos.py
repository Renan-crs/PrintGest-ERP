"""Cache em memória dos catálogos completos usados para preencher combos.

Cada tela (O.S., Venda Balcão, Produtos, grade de itens) recarregava a lista
inteira (`GET ...?limit=1000`) sempre que abria — várias requisições idênticas
por sessão. Aqui o resultado fica guardado por um TTL curto e é invalidado
explicitamente após salvar um registro (`PaginaCrud._salvo`).

O carregamento continua assíncrono (`rodar`): quando o valor está fresco na
cache, o callback de sucesso é chamado imediatamente (mesma thread da UI).
"""

from __future__ import annotations

import time
from typing import Callable

import printgest.core.tarefas as tarefas

_TTL_SEGUNDOS = 300.0

# chave -> (monotonic_timestamp, resposta)
_cache: dict[str, tuple[float, dict]] = {}

# chave -> [(buscador, on_ok, on_erro)] — assinantes vivos. Quando o cache é
# invalidado, eles são recarregados automaticamente na próxima chamada de
# `carregar`, mesmo que a tela já estivesse aberta (RF de atualização).
_assinantes: dict[str, list[tuple[Callable, Callable, Callable]]] = {}


def carregar(
    chave: str,
    buscador: Callable[[], dict],
    on_ok: Callable[[dict], None],
    on_erro: Callable[[str], None] | None = None,
    ttl: float = _TTL_SEGUNDOS,
) -> None:
    """Entrega o catálogo a `on_ok`, servindo da cache enquanto estiver fresco.

    `buscador` só é executado quando não há valor válido em cache.
    """
    registro = (buscador, on_ok, on_erro or (lambda _msg: None))
    assinantes = _assinantes.setdefault(chave, [])
    # `==` (não `is`): bound methods como `lista.append` são objetos novos a
    # cada acesso, mas comparam iguais — evita assinantes duplicados.
    for i, a in enumerate(assinantes):
        if a[1] == on_ok:
            assinantes[i] = registro  # tela reaberta: atualiza referências
            break
    else:
        assinantes.append(registro)

    entrada = _cache.get(chave)
    if entrada is not None and (time.monotonic() - entrada[0]) < ttl:
        on_ok(entrada[1])
        return

    def _recebido(dados: dict) -> None:
        _cache[chave] = (time.monotonic(), dados)
        on_ok(dados)

    tarefas.rodar(buscador, on_ok=_recebido, on_erro=on_erro or (lambda _msg: None))


def invalidar(*chaves: str) -> None:
    """Remove as chaves informadas do cache e recarrega os assinantes vivos.

    Antes, a invalidação só limpava o dicionário: telas já abertas guardavam
    cópias locais (combos de produto, flags de cliente, vendedores) e só
    atualizavam após novo login. Agora os assinantes são recarregados
    automaticamente, propagando a mudança para todas as telas abertas.
    """
    alvos = list(chaves) if chaves else list(_cache)
    for chave in alvos:
        _cache.pop(chave, None)
    for chave in alvos:
        for buscador, on_ok, on_erro in list(_assinantes.get(chave, [])):

            def _recebido(dados: dict, chave=chave, on_ok=on_ok) -> None:
                _cache[chave] = (time.monotonic(), dados)
                on_ok(dados)

            tarefas.rodar(buscador, on_ok=_recebido, on_erro=on_erro)


def limpar() -> None:
    """Esvazia cache e assinantes (usado nos testes para isolar casos)."""
    _cache.clear()
    _assinantes.clear()
