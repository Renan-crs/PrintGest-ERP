"""Controle de acesso (PRD v2.1 §1.1) aplicado à navegação principal.

A matriz não é hierárquica: cada item de menu lista explicitamente os perfis que
o enxergam (`niveis`). Ex.: caixa vê Financeiro/Fiscal enquanto operador não —
isso não é expressável por um "nível mínimo" único. Itens sem permissão **não
aparecem** no menu (o backend reforça com 403/omitindo campos).

Itens granulares (O.S., orçamento, venda balcão, estoque, funcionários…)
saíram do menu v2.1 mas continuam navegáveis via atalho/busca/acesso rápido
através de `ITENS_INTERNOS` e do helper `pode_abrir`.
"""

from __future__ import annotations

RANK = {
    "caixa": 0,
    "operador": 1,
    "gerente": 2,
    "admin": 3,
}


def tem_acesso(nivel: str, nivel_minimo: str) -> bool:
    """True se `nivel` do usuário é igual ou superior a `nivel_minimo`."""
    return RANK.get(nivel, -1) >= RANK.get(nivel_minimo, 99)


# Menu v2.1 (PRD §1 / telas_e_fluxos §1). `niveis` = perfis que veem o item.
MENU = [
    (
        "Operação",
        [
            {"id": "pdv", "rotulo": "PDV", "niveis": ["admin", "gerente", "operador", "caixa"]},
            {"id": "projetos", "rotulo": "Projetos", "niveis": ["admin", "gerente", "operador"]},
            {"id": "agendamento", "rotulo": "Agendamento", "niveis": ["admin", "gerente", "operador"]},
        ],
    ),
    (
        "Cadastros",
        [
            {"id": "cliente", "rotulo": "Clientes", "niveis": ["admin", "gerente", "operador"]},
            {"id": "fornecedor", "rotulo": "Fornecedores", "niveis": ["admin", "gerente"]},
            {"id": "produto", "rotulo": "Produtos", "niveis": ["admin", "gerente", "operador"]},
            {"id": "servico", "rotulo": "Serviços", "niveis": ["admin", "gerente", "operador"]},
            {"id": "categoria", "rotulo": "Categorias", "niveis": ["admin", "gerente", "operador"]},
            {"id": "funcionario", "rotulo": "Funcionários", "niveis": ["admin", "gerente", "operador"]},
        ],
    ),
    (
        "Gestão",
        [
            {"id": "financeiro", "rotulo": "Financeiro", "niveis": ["admin", "gerente", "caixa"]},
            {"id": "fiscal", "rotulo": "Fiscal", "niveis": ["admin", "gerente", "caixa"]},
            {"id": "estoque", "rotulo": "Estoque", "niveis": ["admin", "gerente", "operador"]},
        ],
    ),
    (
        "Relatórios",
        [
            {"id": "relatorios", "rotulo": "Relatórios", "niveis": ["admin", "gerente"]},
        ],
    ),
    (
        "Sistema",
        [
            {"id": "configuracoes", "rotulo": "Configurações", "niveis": ["admin"]},
        ],
    ),
]

ID_MENU = {item["id"] for _grupo, itens in MENU for item in itens}

# Ids granulares que não aparecem no menu v2.1, mas continuam navegáveis
# (atalhos F2/F3/F5, busca global e acesso rápido do Início).
ITENS_INTERNOS = [
    {"id": "os", "rotulo": "Ordem de Serviço", "nivel": "operador"},
    {"id": "orcamento", "rotulo": "Orçamentos", "nivel": "operador"},
    {"id": "venda_balcao", "rotulo": "Venda Balcão", "nivel": "caixa"},
    {"id": "pedido_compra", "rotulo": "Pedido de Compra", "nivel": "operador"},
    {"id": "estoque_consulta", "rotulo": "Consulta de Estoque", "nivel": "operador"},
    {"id": "estoque_movimento", "rotulo": "Movimentação Manual", "nivel": "operador"},
    {"id": "estoque_reposicao", "rotulo": "Relatório de Reposição", "nivel": "operador"},
    {"id": "estoque_mais_vendidos", "rotulo": "Mais Vendidos", "nivel": "operador"},
    {"id": "caixa", "rotulo": "Caixa", "nivel": "caixa"},
    {"id": "contas_receber", "rotulo": "Contas a Receber", "nivel": "gerente"},
    {"id": "contas_pagar", "rotulo": "Contas a Pagar", "nivel": "gerente"},
    {"id": "plano_contas", "rotulo": "Plano de Contas", "nivel": "gerente"},
    {"id": "documentos_fiscais", "rotulo": "Documentos Fiscais", "nivel": "operador"},
    {"id": "contingencia", "rotulo": "Contingência", "nivel": "operador"},
    {"id": "rel_vendas", "rotulo": "Vendas por Período", "nivel": "gerente"},
    {"id": "rel_clientes", "rotulo": "Clientes que Mais Compram", "nivel": "gerente"},
    {"id": "rel_servicos", "rotulo": "Serviços Mais Executados", "nivel": "gerente"},
    {"id": "rel_aniversariantes", "rotulo": "Aniversariantes", "nivel": "gerente"},
    {"id": "dados_empresa", "rotulo": "Dados da Empresa", "nivel": "admin"},
    {"id": "personalizacao", "rotulo": "Personalização", "nivel": "admin"},
    {"id": "reajuste_bloco", "rotulo": "Reajuste de Preços", "nivel": "admin"},
    {"id": "usuarios", "rotulo": "Usuários e Níveis", "nivel": "admin"},
]


def pode_abrir(nivel: str, item_id: str) -> bool:
    """True se o usuário pode navegar para o item (menu v2.1 ou interno)."""
    for _grupo, itens in MENU:
        for item in itens:
            if item["id"] == item_id:
                return nivel in item["niveis"]
    for item in ITENS_INTERNOS:
        if item["id"] == item_id:
            return tem_acesso(nivel, item["nivel"])
    return False


def menu_visivel(nivel: str) -> list[tuple[str, list[dict]]]:
    """Menu filtrado pelo nível do usuário logado: `[(grupo, [itens]), ...]`."""
    return [
        (grupo, [item for item in itens if nivel in item["niveis"]])
        for grupo, itens in MENU
        if any(nivel in item["niveis"] for item in itens)
    ]


def rotulo_do_item(item_id: str) -> str:
    for _grupo, itens in MENU:
        for item in itens:
            if item["id"] == item_id:
                return item["rotulo"]
    for item in ITENS_INTERNOS:
        if item["id"] == item_id:
            return item["rotulo"]
    return item_id


def nivel_rotulo(nivel: str) -> str:
    return {
        "admin": "Administrador",
        "gerente": "Gerente",
        "operador": "Operador",
        "caixa": "Caixa",
    }.get(nivel, nivel)