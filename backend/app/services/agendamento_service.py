"""Serviços do módulo Agendamento (PRD §1.3 / telas_e_fluxos §1.3 — Calendário/Lista).

Compromissos de produção/entrega sobre a tabela `agendamento`. A listagem por
janela de datas usa o teste de sobreposição (`inicio_do_evento <= fim_da_janela`
e `fim_do_evento >= inicio_da_janela`), que é o que o calendário precisa para
exibir o mês inteiro.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cadastros import Cliente
from app.models.enums import StatusAgenda
from app.models.movimento import Agendamento, OrdemServico


def _base(db: Session, filial_id: int):
    return (
        db.query(
            Agendamento,
            OrdemServico.numero.label("os_numero"),
            Cliente.nome_razao.label("cliente_nome"),
        )
        .outerjoin(OrdemServico, Agendamento.ordem_servico_id == OrdemServico.id)
        .outerjoin(Cliente, OrdemServico.cliente_id == Cliente.id)
        .filter(Agendamento.filial_id == filial_id)
    )


def _item(ag: Agendamento, os_numero: int | None, cliente_nome: str | None) -> dict:
    dados = {c.name: getattr(ag, c.name) for c in Agendamento.__table__.columns}
    dados["ordem_servico_numero"] = os_numero
    dados["ordem_servico_cliente"] = cliente_nome
    return dados


def _buscar(db: Session, filial_id: int, item_id: int) -> Agendamento:
    ag = (
        db.query(Agendamento)
        .filter(Agendamento.id == item_id, Agendamento.filial_id == filial_id)
        .first()
    )
    if ag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado.",
        )
    return ag


def listar(
    db: Session,
    *,
    filial_id: int,
    inicio=None,
    fim=None,
    tipo=None,
    status=None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = _base(db, filial_id)
    if inicio is not None:
        # Evento começa antes do fim da janela (ou não tem fim definido).
        query = query.filter(
            (Agendamento.data_hora_fim.is_(None))
            | (Agendamento.data_hora_fim >= inicio)
        )
    if fim is not None:
        query = query.filter(Agendamento.data_hora_inicio <= fim)
    if tipo is not None:
        query = query.filter(Agendamento.tipo == tipo)
    if status is not None:
        query = query.filter(Agendamento.status == status)
    total = query.count()
    linhas = (
        query.order_by(Agendamento.data_hora_inicio.asc(), Agendamento.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_item(ag, numero, cliente) for ag, numero, cliente in linhas], total


def obter(db: Session, *, filial_id: int, item_id: int) -> dict:
    linha = _base(db, filial_id).filter(Agendamento.id == item_id).first()
    if linha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agendamento não encontrado.",
        )
    ag, numero, cliente = linha
    return _item(ag, numero, cliente)


def criar(db: Session, *, filial_id: int, usuario_id: int, dados: dict) -> dict:
    ag = Agendamento(**dados, filial_id=filial_id, usuario_id=usuario_id)
    db.add(ag)
    db.commit()
    db.refresh(ag)
    return obter(db, filial_id=filial_id, item_id=ag.id)


def atualizar(db: Session, *, filial_id: int, item_id: int, dados: dict) -> dict:
    ag = _buscar(db, filial_id, item_id)
    for campo, valor in dados.items():
        if valor is not None:
            setattr(ag, campo, valor)
    db.commit()
    db.refresh(ag)
    return obter(db, filial_id=filial_id, item_id=ag.id)


def concluir(db: Session, *, filial_id: int, item_id: int) -> dict:
    ag = _buscar(db, filial_id, item_id)
    ag.status = StatusAgenda.CONCLUIDO
    db.commit()
    db.refresh(ag)
    return obter(db, filial_id=filial_id, item_id=ag.id)


def remover(db: Session, *, filial_id: int, item_id: int) -> None:
    ag = _buscar(db, filial_id, item_id)
    db.delete(ag)
    db.commit()
