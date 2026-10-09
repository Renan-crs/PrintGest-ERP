"""Módulos de negócio acessíveis a partir da Tela Principal.

Mapeia os ids do menu v2.1 (e os ids granulares internos) para as páginas
entregues. Módulos previstos no PRD mas ainda não entregues caem em um
placeholder honesto (`PaginaEmConstrucao`) — nunca em dados inventados.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from printgest.core.api import Api
from printgest.ui.modulos.clientes import PaginaClientes
from printgest.ui.modulos.categorias import PaginaCategorias
from printgest.ui.modulos.em_construcao import PaginaEmConstrucao
from printgest.ui.modulos.estoque import (
    PaginaEstoqueConsulta,
    PaginaEstoqueMovimento,
    PaginaEstoqueReposicao,
)
from printgest.ui.modulos.fornecedores import PaginaFornecedores
from printgest.ui.modulos.funcionarios import PaginaFuncionarios
from printgest.ui.modulos.os import PaginaOS, PaginaOrcamento, PaginaProjetos
from printgest.ui.modulos.produtos import PaginaProdutos
from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao


def criar_pagina(
    item_id: str, rotulo: str, api: Api, modo_leitura: bool
) -> QWidget:
    """Fábrica de páginas por item de menu (§1). Itens não entregues caem no placeholder."""
    paginas = {
        # menu v2.1 — entregues
        "pdv": PaginaVendaBalcao,
        "projetos": PaginaProjetos,
        "cliente": PaginaClientes,
        "fornecedor": PaginaFornecedores,
        "produto": PaginaProdutos,
        # ids granulares internos (fora do menu v2.1, ainda navegáveis)
        "funcionario": PaginaFuncionarios,
        "categoria": PaginaCategorias,
        "os": PaginaOS,
        "orcamento": PaginaOrcamento,
        "venda_balcao": PaginaVendaBalcao,
        "estoque_consulta": PaginaEstoqueConsulta,
        "estoque_movimento": PaginaEstoqueMovimento,
        "estoque_reposicao": PaginaEstoqueReposicao,
    }
    construtora = paginas.get(item_id, PaginaEmConstrucao)
    if construtora is PaginaEmConstrucao:
        return PaginaEmConstrucao(rotulo)
    return construtora(api, modo_leitura=modo_leitura)