"""Testes do cache de catálogos (reduz requisições repetidas de combos)."""

from __future__ import annotations

from printgest.core import catalogos


def test_carregar_serve_da_cache_na_segunda_chamada(app, pumpar):
    chamadas: list[int] = []

    def buscador():
        chamadas.append(1)
        return {"data": []}

    recebidos: list[dict] = []
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    pumpar(lambda: len(recebidos) == 1)  # 1ª vez: consulta de verdade

    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    # 2ª vez é servida da cache de forma síncrona — sem nova consulta.
    assert len(recebidos) == 2
    assert len(chamadas) == 1


def test_invalidar_forca_nova_consulta(app, pumpar):
    chamadas: list[int] = []

    def buscador():
        chamadas.append(1)
        return {"data": []}

    recebidos: list[dict] = []
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    pumpar(lambda: len(recebidos) == 1)

    # invalidar() recarrega os assinantes vivos automaticamente — telas já
    # abertas recebem o catálogo atualizado sem precisar re-chamar `carregar`.
    catalogos.invalidar("k")
    pumpar(lambda: len(recebidos) == 2)
    assert len(chamadas) == 2

    # Agora a cache está fresca: `carregar` entrega sem nova requisição.
    recebidos.clear()
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    assert len(recebidos) == 1 and len(chamadas) == 2
