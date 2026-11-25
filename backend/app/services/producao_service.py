"""Consumo previsto e baixa real de insumos de itens de OS (guia V2).

A baixa segue exatamente o padrão de `venda_service._baixar_estoque`: UPDATE
otimista `WHERE saldo >= :qtd`, `rowcount != 1` → 409, kardex com SAIDA negativa
e `OrigemMov.ORDEM_SERVICO`. `baixado_em` impede baixa duplicada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.models.cadastros import MovimentoEstoque, ProdutoEstoque
from app.models.enums import OrigemMov, TipoMovEstoque
from app.models.movimento import OrdemServico, OrdemServicoItem
from app.models.producao import FichaConsumo, OsItemConsumo
from app.schemas.producao import BaixarConsumoIn
from app.services.custo_service import (
    fichas_vigentes,
    quantidade_prevista,
)


def prever_consumo(
    db: Session, *, filial_id: int, item: OrdemServicoItem
) -> int:
    """Grava/atualiza o consumo previsto do item a partir das fichas vigentes.

    Linhas já baixadas nunca são alteradas. Retorna quantas linhas foram
    gravadas. Item sem produto ou sem ficha não gera nada — o legado segue
    intacto (itens avulsos, cotações de terceirizado).
    """
    if item.produto_id is None:
        return 0
    fichas = fichas_vigentes(db, filial_id=filial_id, produto_id=item.produto_id)
    if not fichas:
        return 0

    gravadas = 0
    for ficha in fichas:
        atual = (
            db.query(OsItemConsumo)
            .filter(
                OsItemConsumo.ordem_servico_item_id == item.id,
                OsItemConsumo.insumo_id == ficha.insumo_id,
            )
            .first()
        )
        if atual is not None and atual.baixado_em is not None:
            continue
        qtd = quantidade_prevista(
            quantidade_por_unidade=ficha.quantidade_por_unidade,
            perda_percentual=ficha.perda_percentual,
            quantidade=item.quantidade,
        )
        if atual is None:
            atual = OsItemConsumo(
                uuid=str(uuid4()),
                filial_id=filial_id,
                ordem_servico_item_id=item.id,
                insumo_id=ficha.insumo_id,
            )
            db.add(atual)
        atual.quantidade_prevista = qtd
        atual.ficha_consumo_id = ficha.id
        atual.custo_unitario_previsto = ficha.custo_processo_unitario
        gravadas += 1
    db.commit()
    return gravadas


def baixar_consumo(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    item_id: int,
    usuario_id: int,
    body: BaixarConsumoIn,
) -> list[OsItemConsumo]:
    """Baixa o consumo real com UPDATE atômico; idempotente por `baixado_em`."""
    item = (
        db.query(OrdemServicoItem)
        .join(OrdemServico, OrdemServicoItem.ordem_servico_id == OrdemServico.id)
        .filter(
            OrdemServicoItem.id == item_id,
            OrdemServico.id == os_id,
            OrdemServico.filial_id == filial_id,
        )
        .first()
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item de OS não encontrado."
        )

    consumos = (
        db.query(OsItemConsumo)
        .filter(OsItemConsumo.ordem_servico_item_id == item_id)
        .order_by(OsItemConsumo.id)
        .all()
    )
    if not consumos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este item não possui ficha de consumo.",
        )
    if all(c.baixado_em is not None for c in consumos):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O consumo deste item já foi baixado.",
        )

    agora = datetime.now(UTC)
    for consumo in consumos:
        if consumo.baixado_em is not None:
            continue
        quantidade = (
            Decimal(str(body.quantidades[consumo.insumo_id]))
            if body.quantidades and consumo.insumo_id in body.quantidades
            else consumo.quantidade_prevista
        )
        if quantidade <= 0:
            continue

        resultado = db.execute(
            sa_text(
                "UPDATE produto_estoque SET saldo = saldo - :qtd, "
                "atualizado_em = now() "
                "WHERE filial_id = :filial AND produto_id = :produto "
                "AND saldo >= :qtd"
            ),
            {
                "qtd": quantidade,
                "filial": filial_id,
                "produto": consumo.insumo_id,
            },
        )
        if resultado.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Estoque insuficiente para o insumo {consumo.insumo_id}.",
            )

        saldo_final = Decimal(
            db.execute(
                sa_text(
                    "SELECT saldo FROM produto_estoque "
                    "WHERE filial_id = :filial AND produto_id = :produto"
                ),
                {"filial": filial_id, "produto": consumo.insumo_id},
            ).scalar_one()
        )
        saldo_anterior = saldo_final + quantidade
        db.add(
            MovimentoEstoque(
                filial_id=filial_id,
                produto_id=consumo.insumo_id,
                tipo=TipoMovEstoque.SAIDA,
                origem=OrigemMov.ORDEM_SERVICO,
                documento_id=item_id,
                # Convenção do kardex: SAIDA negativa.
                quantidade=-quantidade,
                saldo_anterior=saldo_anterior,
                saldo_posterior=saldo_final,
                motivo=body.motivo_perda or "Consumo de produção (OS)",
                usuario_id=usuario_id,
            )
        )
        consumo.quantidade_real = quantidade
        consumo.baixado_em = agora
        consumo.baixado_por = usuario_id
        consumo.motivo_perda = body.motivo_perda

    item.executado = True
    db.commit()
    return consumos
