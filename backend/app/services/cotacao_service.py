"""Cotações de fornecedor para itens terceirizados (M1, PRD v3.0 §3.2.2/§3.2.3).

Fluxo: item de fornecedor nasce **"Aguardando cotação"** (valor 0, não vai ao
cliente); quem tem permissão lança cotações (VF, validade, prazo); **uma** é
selecionada — só ela compõe o orçamento: o `valor_unitario` do item assume o
**VO** calculado (`precificacao`), o snapshot é gravado e os totais da OS são
reprocessados.

Confidencialidade (§3.2.3): VF/CP/percentuais são informação interna. O mapeamento
das permissões por campo para os níveis atuais:

| Permissão PRD | Níveis |
| --- | --- |
| `ver_custo_terceiro` | Admin, Gerente |
| `lancar_cotacao` | Admin, Gerente (padrão; "configurável" fica para o M2) |

A API **omite** os campos sensíveis (nunca "oculta"): o comparativo de um
Operador não contém `vf` em lugar nenhum — teste de aceite do PRD.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.cadastros import Fornecedor
from app.models.enums import NivelAcesso, TipoItemOs
from app.models.movimento import OrdemServico, OrdemServicoItem, OrdemServicoItemCotacao
from app.services import precificacao

_PODE_VER_CUSTO = (NivelAcesso.ADMIN, NivelAcesso.GERENTE)
_CENTAVOS = Decimal("0.01")


def pode_ver_custo(usuario) -> bool:
    """`ver_custo_terceiro` (§3.2.3) — Admin/Gerente no RBAC atual."""
    return getattr(usuario, "nivel_acesso", None) in _PODE_VER_CUSTO


def _obter_item(db: Session, item_id: int, *, filial_id: int) -> OrdemServicoItem:
    item = (
        db.query(OrdemServicoItem)
        .join(OrdemServico)
        .options(joinedload(OrdemServicoItem.cotacoes))
        .filter(
            OrdemServicoItem.id == item_id,
            OrdemServico.filial_id == filial_id,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado nesta filial.")
    return item


def _exigir_item_fornecedor(item: OrdemServicoItem) -> None:
    if item.tipo != TipoItemOs.FORNECEDOR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cotações existem apenas para itens de fornecedor.",
        )


def para_out(cotacao: OrdemServicoItemCotacao, *, ver_custo: bool) -> dict:
    """Serializa com a regra de omissão: sem `ver_custo_terceiro`, sem `vf`."""
    saida = {
        "id": cotacao.id,
        "fornecedor_id": cotacao.fornecedor_id,
        "fornecedor_nome": cotacao.fornecedor.nome_razao if cotacao.fornecedor else None,
        "validade": cotacao.validade,
        "prazo_dias": cotacao.prazo_dias,
        "observacoes": cotacao.observacoes,
        "selecionada": cotacao.selecionada,
        "criado_em": cotacao.criado_em,
    }
    if ver_custo:
        saida["vf"] = cotacao.vf
    return saida


def _snapshot_para_gerente(item: OrdemServicoItem, *, ver_custo: bool) -> dict | None:
    """Snapshot do cálculo (VF/CP/VO) do item — só para quem pode ver custo."""
    if not ver_custo or not item.snapshot_preco:
        return None
    return dict(item.snapshot_preco)


def _aplicar_selecao(
    db: Session,
    *,
    item: OrdemServicoItem,
    cotacao: OrdemServicoItemCotacao,
    filial_id: int,
) -> None:
    """Marca a cotação como a única selecionada e recalcula o item + a OS.

    O VO calculado assume o `valor_unitario` do item (é o que o cliente paga);
    o snapshot (VF, percentuais, CP, VO) fica gravado no item (§3.2.1) — mudar
    os parâmetros globais depois não altera este item.
    """
    for outra in item.cotacoes:
        outra.selecionada = outra.id == cotacao.id
    cotacao.selecionada = True

    snapshot = precificacao.calcular_item_terceirizado(
        db, filial_id=filial_id, vf=cotacao.vf,
        fornecedor_id=cotacao.fornecedor_id,  # M2: sobrescrita do fornecedor
    )
    item.snapshot_preco = snapshot
    item.valor_unitario = Decimal(snapshot["vo"])
    item.valor_total = (
        item.valor_unitario * item.quantidade - item.desconto
    ).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    if item.valor_total < 0:
        item.valor_total = Decimal("0.00")

    _recalcular_totais_os(db, item.os)


def _recalcular_totais_os(db: Session, os_obj: OrdemServico) -> None:
    """Totais da OS a partir dos itens (mantém a invariável itens − desconto)."""
    valor_itens = sum((i.valor_total for i in os_obj.itens), Decimal("0")).quantize(
        _CENTAVOS, rounding=ROUND_HALF_UP
    )
    os_obj.valor_itens = valor_itens
    os_obj.valor_total = (valor_itens - os_obj.desconto).quantize(
        _CENTAVOS, rounding=ROUND_HALF_UP
    )


def lancar(
    db: Session,
    *,
    item_id: int,
    filial_id: int,
    usuario,
    dados,
) -> dict:
    item = _obter_item(db, item_id, filial_id=filial_id)
    _exigir_item_fornecedor(item)

    fornecedor = db.get(Fornecedor, dados.fornecedor_id)
    if fornecedor is None:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado.")

    cotacao = OrdemServicoItemCotacao(
        item_id=item.id,
        fornecedor_id=dados.fornecedor_id,
        vf=dados.vf,
        validade=dados.validade,
        prazo_dias=dados.prazo_dias,
        observacoes=dados.observacoes,
        criado_por=usuario.id,
    )
    db.add(cotacao)
    db.flush()
    if dados.selecionada:
        _aplicar_selecao(db, item=item, cotacao=cotacao, filial_id=filial_id)
    db.commit()
    db.refresh(cotacao)
    return para_out(cotacao, ver_custo=pode_ver_custo(usuario))


def selecionar(
    db: Session,
    *,
    item_id: int,
    cotacao_id: int,
    filial_id: int,
    usuario,
) -> dict:
    item = _obter_item(db, item_id, filial_id=filial_id)
    _exigir_item_fornecedor(item)
    cotacao = next((c for c in item.cotacoes if c.id == cotacao_id), None)
    if cotacao is None:
        raise HTTPException(status_code=404, detail="Cotação não encontrada para este item.")

    _aplicar_selecao(db, item=item, cotacao=cotacao, filial_id=filial_id)
    db.commit()
    db.refresh(cotacao)
    return para_out(cotacao, ver_custo=pode_ver_custo(usuario))


def listar(
    db: Session,
    *,
    item_id: int,
    filial_id: int,
    usuario,
) -> dict:
    """Comparativo interno (VF, prazo, validade — §3.2.2 item 5) + snapshot."""
    item = _obter_item(db, item_id, filial_id=filial_id)
    ver_custo = pode_ver_custo(usuario)
    cotacoes = sorted(item.cotacoes, key=lambda c: c.criado_em)
    return {
        "data": [para_out(c, ver_custo=ver_custo) for c in cotacoes],
        "estado_cotacao": (
            "cotado"
            if item.tipo == TipoItemOs.FORNECEDOR
            and any(c.selecionada for c in item.cotacoes)
            else ("aguardando" if item.tipo == TipoItemOs.FORNECEDOR else None)
        ),
        "selecionado": _snapshot_para_gerente(item, ver_custo=ver_custo),
    }
