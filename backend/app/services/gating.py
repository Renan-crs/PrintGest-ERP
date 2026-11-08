"""Gating de módulos por plano (PRD v3.0 §2): rota sem módulo habilitado → 403.

Os planos (Essencial/Profissional/Enterprise) habilitam conjuntos de módulos
emitidos pelo RedGest em `entitlements.modulos`. Regras do PRD:

- o bloqueio é **no servidor** (o desktop só oculta o menu);
- `entitlements` ausente ou malformado **não libera nenhum módulo** — o
  `_recalcular_estado` da licença só junta strings válidas de `modulos`;
- o Início (dashboard operacional) fica fora do mapa: é de todos os planos
  (`relatorios` gerenciais é outro módulo, quando existir).

Armar/desarmar: `PRINTGEST_GATING_MODULOS=true` (padrão desligado). A mesma
lição da `api_key` do Contrato C: o mecanismo entra testado e apontando para o
RedGest, e a chave só liga quando o RedGest passa a emitir `modulos` — antes
disso, ligar a flag bloquearia projetos/financeiro/fiscal do piloto real, cuja
licença PARCERIA ainda não carrega a lista.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services import licensa_service

# Prefixo → módulo canônico (PRD v3.0 §2), na ordem: mais específico primeiro.
# `caixa` (abertura/fechamento/sangria + contas a receber simples) é do plano
# Essencial; o RESTO do financeiro (contas a pagar, plano de contas) é do
# Profissional — por isso as rotas de caixa são casadas antes do prefixo pai.
_ROTAS_MODULOS: tuple[tuple[str, str], ...] = (
    ("/v1/financeiro/caixa", "caixa"),
    ("/v1/financeiro/contas-receber", "caixa"),
    ("/v1/financeiro", "financeiro"),
    ("/v1/clientes", "cadastros"),
    ("/v1/fornecedores", "cadastros"),
    ("/v1/produtos", "cadastros"),
    ("/v1/servicos", "cadastros"),
    ("/v1/categorias", "cadastros"),
    ("/v1/funcionarios", "cadastros"),
    ("/v1/os", "movimento"),
    ("/v1/vendas", "movimento"),
    ("/v1/agendamento", "agendamento"),
    ("/v1/estoque", "estoque"),
    ("/v1/projetos", "projetos"),
    ("/v1/fiscal", "fiscal"),
    ("/v1/config", "configuracoes"),
    ("/v1/usuarios", "configuracoes"),
    # Rotas futuras (custos, compras, arte, produção, relatórios) entram aqui
    # quando existirem — o id canônico já está na matriz do PRD §2.
)

_NOMES_MODULOS: dict[str, str] = {
    "cadastros": "Cadastros",
    "movimento": "Movimento (OS/Orçamento/PDV)",
    "estoque": "Estoque",
    "agendamento": "Agendamento",
    "caixa": "Caixa",
    "configuracoes": "Configurações",
    "custos": "Custos",
    "estoque_avancado": "Estoque avançado",
    "compras": "Compras",
    "arte": "Arte",
    "producao": "Produção",
    "projetos": "Projetos",
    "financeiro": "Financeiro",
    "relatorios": "Relatórios",
    "fiscal": "Fiscal",
    "multifilial": "Multi-filial",
    "api_integracao": "API de integração",
}


def modulo_da_rota(caminho: str) -> str | None:
    """Módulo que responde pela rota; `None` = de todos os planos (ou interna)."""
    for prefixo, modulo in _ROTAS_MODULOS:
        if caminho.startswith(prefixo):
            return modulo
    return None


def rota_bloqueada(caminho: str, modulos_habilitados: set[str]) -> str | None:
    """Módulo bloqueado para a rota, ou `None` quando liberada."""
    if not settings.gating_modulos:
        return None
    modulo = modulo_da_rota(caminho)
    if modulo is not None and modulo not in modulos_habilitados:
        return modulo
    return None


async def controle_modulos(request: Request, call_next):
    """Middleware transversal: módulo não habilitado responde `403` (PRD §2)."""
    bloqueado = rota_bloqueada(request.url.path, licensa_service.MODULOS_HABILITADOS)
    if bloqueado is not None:
        nome = _NOMES_MODULOS.get(bloqueado, bloqueado)
        return JSONResponse(
            status_code=403,
            content={
                "detail": f"O módulo {nome} não está habilitado no seu plano.",
                "codigo": "MODULO_BLOQUEADO",
                "modulo": bloqueado,
            },
        )
    return await call_next(request)
