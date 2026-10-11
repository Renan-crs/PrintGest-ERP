"""Serviços do módulo Fiscal (PRD §1.3 / telas_e_fluxos §1.6) — somente leitura.

A emissão/reprocessamento de NF-e/NFC-e exige um gateway fiscal externo que não
existe neste repositório; por isso este serviço apenas **consulta** os documentos
persistidos e resume a situação para a tela de contingência.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.models.cadastros import Cliente
from app.models.enums import StatusFiscal
from app.models.fiscal import DocumentoFiscal

# O gateway fiscal não faz parte deste produto: enquanto não for integrado, a
# emissão fica indisponível e a tela de contingência avisa o usuário.
GATEWAY_CONFIGURADO = False
_MENSAGEM_GATEWAY = (
    "Gateway fiscal não configurado — a emissão de NF-e/NFC-e está indisponível. "
    "Os documentos podem ser consultados e as pendências acompanhadas nesta tela; "
    "a emissão será liberada quando o gateway for integrado."
)

_STATUS_PENDENTES = (
    StatusFiscal.RASCUNHO,
    StatusFiscal.PROCESSANDO,
    StatusFiscal.REJEITADO,
)


def _base(db: Session, filial_id: int):
    return (
        db.query(DocumentoFiscal, Cliente.nome_razao)
        .outerjoin(Cliente, DocumentoFiscal.cliente_id == Cliente.id)
        .filter(DocumentoFiscal.filial_id == filial_id)
    )


def _item(doc: DocumentoFiscal, cliente_nome: str | None) -> dict:
    dados = {c.name: getattr(doc, c.name) for c in DocumentoFiscal.__table__.columns}
    dados["cliente_nome"] = cliente_nome
    return dados


def listar_documentos(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    modelo: str | None = None,
    status_fiscal: StatusFiscal | None = None,
    contingencia: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = _base(db, filial_id)
    if modelo is not None:
        query = query.filter(DocumentoFiscal.modelo == modelo)
    if status_fiscal is not None:
        query = query.filter(DocumentoFiscal.status == status_fiscal)
    if contingencia is not None:
        query = query.filter(DocumentoFiscal.contingencia.is_(contingencia))
    termo = (q or "").strip()
    if termo:
        query = query.filter(
            or_(
                DocumentoFiscal.chave_acesso.ilike(f"%{termo}%"),
                Cliente.nome_razao.ilike(f"%{termo}%"),
                cast(DocumentoFiscal.numero, String).ilike(f"%{termo}%"),
            )
        )
    total = query.count()
    linhas = (
        query.order_by(DocumentoFiscal.created_at.desc(), DocumentoFiscal.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_item(doc, nome) for doc, nome in linhas], total


def obter_documento(db: Session, *, item_id: int, filial_id: int) -> dict:
    linha = _base(db, filial_id).filter(DocumentoFiscal.id == item_id).first()
    if linha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento fiscal não encontrado.",
        )
    doc, nome = linha
    return _item(doc, nome)


def resumo(db: Session, *, filial_id: int) -> dict:
    por_status = {
        chave.value: total
        for chave, total in db.query(
            DocumentoFiscal.status, func.count(DocumentoFiscal.id)
        )
        .filter(DocumentoFiscal.filial_id == filial_id)
        .group_by(DocumentoFiscal.status)
        .all()
    }
    por_modelo = {
        chave.value: total
        for chave, total in db.query(
            DocumentoFiscal.modelo, func.count(DocumentoFiscal.id)
        )
        .filter(DocumentoFiscal.filial_id == filial_id)
        .group_by(DocumentoFiscal.modelo)
        .all()
    }
    total = sum(por_status.values())
    pendentes = sum(por_status.get(s.value, 0) for s in _STATUS_PENDENTES)
    em_contingencia = (
        db.query(func.count(DocumentoFiscal.id))
        .filter(
            DocumentoFiscal.filial_id == filial_id,
            DocumentoFiscal.contingencia.is_(True),
        )
        .scalar()
        or 0
    )
    return {
        "total": total,
        "por_status": por_status,
        "por_modelo": por_modelo,
        "pendentes": pendentes,
        "em_contingencia": em_contingencia,
        "gateway_configurado": GATEWAY_CONFIGURADO,
        "gateway_disponivel": False,
        "mensagem": _MENSAGEM_GATEWAY,
    }
