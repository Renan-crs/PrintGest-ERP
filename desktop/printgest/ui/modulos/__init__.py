"""Módulos de negócio acessíveis a partir da Tela Principal.

Mapeia os ids do menu v2.1 (e os ids granulares internos) para as páginas
entregues. Módulos previstos no PRD mas ainda não entregues caem em um
placeholder honesto (`PaginaEmConstrucao`) — nunca em dados inventados.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from printgest.core.api import Api
from printgest.ui.modulos.agendamento import PaginaAgendamento
from printgest.ui.modulos.clientes import PaginaClientes
from printgest.ui.modulos.categorias import PaginaCategorias
from printgest.ui.modulos.configuracao import (
    PaginaConfiguracoes,
    PaginaEmpresa,
    PaginaPersonalizacao,
    PaginaReajuste,
    PaginaUsuarios,
)
from printgest.ui.modulos.em_construcao import PaginaEmConstrucao
from printgest.ui.modulos.estoque import (
    PaginaEstoque,
    PaginaEstoqueConsulta,
    PaginaEstoqueMovimento,
    PaginaEstoqueReposicao,
)
from printgest.ui.modulos.financeiro import (
    PaginaCaixa,
    PaginaContasPagar,
    PaginaContasReceber,
    PaginaFinanceiro,
    PaginaPlanoContas,
)
from printgest.ui.modulos.fiscal import (
    PaginaContingencia,
    PaginaDocumentosFiscais,
    PaginaFiscal,
)
from printgest.ui.modulos.fornecedores import PaginaFornecedores
from printgest.ui.modulos.funcionarios import PaginaFuncionarios
from printgest.ui.modulos.os import PaginaOS, PaginaOrcamento
from printgest.ui.modulos.produtos import PaginaProdutos, PaginaServicos
from printgest.ui.modulos.projetos import PaginaProjetos
from printgest.ui.modulos.relatorios import PaginaRelatorios
from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao


def criar_pagina(
    item_id: str, rotulo: str, api: Api, modo_leitura: bool, nivel: str | None = None
) -> QWidget:
    """Fábrica de páginas por item de menu (§1). Itens não entregues caem no placeholder."""
    paginas = {
        # menu v2.1 — entregues
        "pdv": PaginaVendaBalcao,
        "projetos": PaginaProjetos,
        "agendamento": PaginaAgendamento,
        "cliente": PaginaClientes,
        "fornecedor": PaginaFornecedores,
        "produto": PaginaProdutos,
        "servico": PaginaServicos,
        "categoria": PaginaCategorias,
        "funcionario": PaginaFuncionarios,
        "financeiro": PaginaFinanceiro,
        "fiscal": PaginaFiscal,
        "estoque": PaginaEstoque,
        "relatorios": PaginaRelatorios,
        "configuracoes": PaginaConfiguracoes,
        # ids granulares internos (fora do menu v2.1, ainda navegáveis)
        "os": PaginaOS,
        "orcamento": PaginaOrcamento,
        "venda_balcao": PaginaVendaBalcao,
        "estoque_consulta": PaginaEstoqueConsulta,
        "estoque_movimento": PaginaEstoqueMovimento,
        "estoque_reposicao": PaginaEstoqueReposicao,
        "caixa": PaginaCaixa,
        "contas_receber": PaginaContasReceber,
        "contas_pagar": PaginaContasPagar,
        "plano_contas": PaginaPlanoContas,
        "documentos_fiscais": PaginaDocumentosFiscais,
        "contingencia": PaginaContingencia,
        "dados_empresa": PaginaEmpresa,
        "personalizacao": PaginaPersonalizacao,
        "reajuste_bloco": PaginaReajuste,
        "usuarios": PaginaUsuarios,
    }
    construtora = paginas.get(item_id, PaginaEmConstrucao)
    if construtora is PaginaEmConstrucao:
        return PaginaEmConstrucao(rotulo)
    if construtora is PaginaFinanceiro:
        # O host de Financeiro esconde as abas que o perfil não pode abrir.
        return PaginaFinanceiro(api, modo_leitura=modo_leitura, nivel=nivel)
    if construtora is PaginaFiscal:
        # O host de Fiscal também recebe o nível (abas por perfil).
        return PaginaFiscal(api, modo_leitura=modo_leitura, nivel=nivel)
    if construtora is PaginaConfiguracoes:
        # O host de Configuração também recebe o nível (abas por perfil).
        return PaginaConfiguracoes(api, modo_leitura=modo_leitura, nivel=nivel)
    if construtora is PaginaVendaBalcao:
        # O PDV usa o nível para esconder ações que o perfil não pode executar.
        return PaginaVendaBalcao(api, modo_leitura=modo_leitura, nivel=nivel)
    if construtora is PaginaProjetos:
        # O quadro esconde a estrutura de listas para quem não é gestor.
        return PaginaProjetos(api, modo_leitura=modo_leitura, nivel=nivel)
    if construtora in (PaginaProdutos, PaginaServicos):
        # Operador não edita preços (RBAC §1.1); o backend segue a mesma regra.
        return construtora(api, modo_leitura=modo_leitura, nivel=nivel)
    return construtora(api, modo_leitura=modo_leitura)
