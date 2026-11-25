"""Custo de produção, margem bruta e consumo previsto — guia V2 (RF-VR-16/17/20).

O cálculo é determinístico; a persistência das fichas é tratada à parte.
`custo_processo_unitario` é por **unidade do produto** (não por insumo): quando
há várias fichas vigentes para o mesmo produto, usa-se o maior valor para não
contar duas vezes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cadastros import Produto
from app.models.producao import FichaConsumo

_CENTAVOS = Decimal("0.01")
_QUATRO = Decimal("0.0001")
_MIL = Decimal("0.001")
_CEM = Decimal("100")


def _decimal(valor) -> Decimal:
    return Decimal(str(valor))


def calcular_custo_unitario(
    fichas: Sequence[FichaConsumo], custos_dos_insumos: dict[int, Decimal]
) -> tuple[Decimal, list[dict], list[str]]:
    """Devolve `(custo_unitário, consumo_previsto_por_unidade, alertas)`."""
    consumo: list[dict] = []
    alertas: list[str] = []
    total = Decimal("0")
    processos: list[Decimal] = []

    for ficha in fichas:
        custo_insumo = custos_dos_insumos.get(ficha.insumo_id)
        if custo_insumo is None:
            alertas.append(f"Insumo {ficha.insumo_id} sem custo cadastrado.")
            custo_insumo = Decimal("0")
        perda = _decimal(ficha.perda_percentual) / _CEM
        quantidade = _decimal(ficha.quantidade_por_unidade) * (Decimal("1") + perda)
        total += quantidade * custo_insumo
        consumo.append(
            {
                "insumo_id": ficha.insumo_id,
                "ficha_consumo_id": ficha.id,
                "quantidade_por_unidade": quantidade.quantize(_QUATRO, rounding=ROUND_HALF_UP),
                "custo_unitario": custo_insumo,
                "perda_percentual": _decimal(ficha.perda_percentual),
            }
        )
        processo = _decimal(ficha.custo_processo_unitario)
        if processo > 0:
            processos.append(processo)

    if processos:
        total += max(processos)
    return total.quantize(_QUATRO, rounding=ROUND_HALF_UP), consumo, alertas


def calcular_margem_bruta(preco_unitario: Decimal, custo_unitario: Decimal) -> Decimal | None:
    """Margem sobre o preço final; `None` sem preço (evita divisão por zero)."""
    preco, custo = _decimal(preco_unitario), _decimal(custo_unitario)
    if preco <= 0:
        return None
    return ((preco - custo) / preco).quantize(_QUATRO, rounding=ROUND_HALF_UP)


def fichas_vigentes(
    db: Session, *, filial_id: int, produto_id: int, data: datetime | None = None
) -> list[FichaConsumo]:
    agora = data or datetime.now(UTC)
    return (
        db.query(FichaConsumo)
        .filter(
            FichaConsumo.filial_id == filial_id,
            FichaConsumo.produto_id == produto_id,
            FichaConsumo.ativo.is_(True),
            FichaConsumo.vigencia_inicio <= agora,
            or_(
                FichaConsumo.vigencia_fim.is_(None),
                FichaConsumo.vigencia_fim > agora,
            ),
        )
        .order_by(FichaConsumo.id)
        .all()
    )


def calcular_custo_no_banco(
    db: Session, *, filial_id: int, produto_id: int, data: datetime | None = None
) -> tuple[Decimal, list[dict], list[str]]:
    fichas = fichas_vigentes(db, filial_id=filial_id, produto_id=produto_id, data=data)
    if not fichas:
        return Decimal("0.0000"), [], []
    ids = {f.insumo_id for f in fichas}
    custos: dict[int, Decimal] = {}
    for insumo_id in ids:
        insumo = db.get(Produto, insumo_id)
        if insumo is not None and insumo.filial_id == filial_id:
            custos[insumo_id] = _decimal(insumo.preco_custo or 0)
    return calcular_custo_unitario(fichas, custos)


def custo_e_margem(
    db: Session,
    *,
    filial_id: int,
    produto_id: int | None,
    preco_unitario: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """Custo e margem do produto; `(None, None)` quando não há ficha vigente."""
    if produto_id is None:
        return None, None
    fichas = fichas_vigentes(db, filial_id=filial_id, produto_id=produto_id)
    if not fichas:
        return None, None
    custos: dict[int, Decimal] = {}
    for insumo_id in {f.insumo_id for f in fichas}:
        insumo = db.get(Produto, insumo_id)
        if insumo is not None and insumo.filial_id == filial_id:
            custos[insumo_id] = _decimal(insumo.preco_custo or 0)
    custo, _, _ = calcular_custo_unitario(fichas, custos)
    return custo, calcular_margem_bruta(preco_unitario, custo)


def quantidade_prevista(
    *, quantidade_por_unidade: Decimal, perda_percentual: Decimal, quantidade: Decimal
) -> Decimal:
    """Consumo previsto de um insumo para `quantidade` unidades do produto."""
    perda = _decimal(perda_percentual) / _CEM
    return (
        _decimal(quantidade_por_unidade)
        * (Decimal("1") + perda)
        * _decimal(quantidade)
    ).quantize(_MIL, rounding=ROUND_HALF_UP)


def erro_sem_saldo(insumo_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Estoque insuficiente para o insumo {insumo_id}.",
    )
