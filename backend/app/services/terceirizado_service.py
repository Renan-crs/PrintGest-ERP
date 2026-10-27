"""Rastreio de terceirizados na OS (M4, PRD v3.0 §3.6).

Ciclo do item terceirizado: **enviado** → **previsão** → **retornado** →
**conferido**. O atraso (previsão vencida sem retorno) alimenta o dashboard.

A criação é automática: quando a cotação é selecionada (M1, §3.2.2), o
`cotacao_service` chama `registrar_envio` — a etapa nasce com `data_envio`
de hoje e `previsao_retorno` a partir do prazo da cotação (§3.6: "agendamento
passa a sugerir datas a partir do prazo de entrega do fornecedor").
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import ConferenciaTerceirizado, TipoItemOs
from app.models.movimento import OrdemServico, OrdemServicoItem, OsTerceirizado


def registrar_envio(
    db: Session,
    *,
    os_id: int,
    filial_id: int,
    item_id: int,
    cotacao_id: int | None = None,
    pedido_compra_id: int | None = None,
    prazo_dias: int | None = None,
    usuario_id: int | None = None,
) -> OsTerceirizado:
    """Cria a etapa "Terceirizado" quando a cotação é selecionada (§3.6).

    Idempotente: se o item já tem rastreio, devolve o existente.
    """
    existente = (
        db.query(OsTerceirizado)
        .filter(OsTerceirizado.item_id == item_id)
        .first()
    )
    if existente is not None:
        return existente

    hoje = date.today()
    envio = OsTerceirizado(
        filial_id=filial_id,
        os_id=os_id,
        item_id=item_id,
        cotacao_id=cotacao_id,
        pedido_compra_id=pedido_compra_id,
        data_envio=hoje,
        previsao_retorno=(
            hoje + timedelta(days=prazo_dias) if prazo_dias is not None else None
        ),
        criado_por=usuario_id,
    )
    db.add(envio)
    db.flush()
    return envio


def _obter(db: Session, item_id: int, *, filial_id: int) -> OsTerceirizado:
    envio = (
        db.query(OsTerceirizado)
        .join(OrdemServico)
        .filter(
            OsTerceirizado.item_id == item_id,
            OrdemServico.filial_id == filial_id,
        )
        .first()
    )
    if envio is None:
        raise HTTPException(
            status_code=404,
            detail="Este item não tem rastreio de terceirizado (selecione a cotação primeiro).",
        )
    return envio


def marcar_retorno(
    db: Session,
    *,
    item_id: int,
    filial_id: int,
    data_retorno: date | None = None,
) -> OsTerceirizado:
    """Marca o retorno do fornecedor (§3.6: "recebido (data)")."""
    envio = _obter(db, item_id, filial_id=filial_id)
    if envio.data_retorno is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Retorno já registrado em {envio.data_retorno}.",
        )
    envio.data_retorno = data_retorno or date.today()
    db.commit()
    db.refresh(envio)
    return envio


def marcar_conferencia(
    db: Session,
    *,
    item_id: int,
    filial_id: int,
    conferencia: ConferenciaTerceirizado,
    observacoes: str | None = None,
) -> OsTerceirizado:
    """Conferência de qualidade: ok / refação (§3.6)."""
    envio = _obter(db, item_id, filial_id=filial_id)
    if envio.data_retorno is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registre o retorno antes de conferir a qualidade.",
        )
    envio.conferencia = (
        conferencia.value if hasattr(conferencia, "value") else str(conferencia)
    )
    if observacoes is not None:
        envio.observacoes = observacoes
    db.commit()
    db.refresh(envio)
    return envio


def atrasados(db: Session, *, filial_id: int) -> list[OsTerceirizado]:
    """Rastreios com previsão vencida sem retorno — para o sino/dashboard."""
    hoje = date.today()
    return (
        db.query(OsTerceirizado)
        .join(OrdemServico)
        .filter(
            OrdemServico.filial_id == filial_id,
            OsTerceirizado.data_retorno.is_(None),
            OsTerceirizado.previsao_retorno.isnot(None),
            OsTerceirizado.previsao_retorno < hoje,
        )
        .all()
    )


def para_out(envio: OsTerceirizado, *, item: OrdemServicoItem | None = None) -> dict:
    """Serializa o rastreio para a resposta da API."""
    hoje = date.today()
    atrasado = (
        envio.data_retorno is None
        and envio.previsao_retorno is not None
        and envio.previsao_retorno < hoje
    )
    return {
        "id": envio.id,
        "os_id": envio.os_id,
        "item_id": envio.item_id,
        "data_envio": envio.data_envio,
        "previsao_retorno": envio.previsao_retorno,
        "data_retorno": envio.data_retorno,
        "conferencia": envio.conferencia,
        "observacoes": envio.observacoes,
        "atrasado": atrasado,
        "descricao_item": (
            item.descricao_avulsa if item is not None else None
        ),
    }
