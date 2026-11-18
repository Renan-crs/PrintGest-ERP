"""Transferência de estoque entre filiais — fluxo de dois passos (PRD §5.6).

- `registrar_saida`: origem baixa estoque (UPDATE ... WHERE saldo >= qtd) e
  grava kardex `TRANSFERENCIA_SAIDA`. Documento fica `enviada`.
- `confirmar_recebimento`: destino soma estoque e grava kardex
  `TRANSFERENCIA_ENTRADA`. Documento fica `recebida`.
- `cancelar`: estorna a saída na origem se ainda não recebida.

O estoque do destino só é somado após a confirmação. Sem transação
distribuída: cada filial escreve apenas no seu próprio `filial_id`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.models.enums import (
    EstadoTransferencia,
    OrigemMov,
    TipoMovEstoque,
)
from app.models.cadastros import MovimentoEstoque
from app.models.core import Filial
from app.models.transferencia import TransferenciaEstoque

def _saldo(db: Session, filial_id: int, produto_id: int) -> Decimal:
    valor = db.execute(
        sa_text(
            "SELECT saldo FROM produto_estoque "
            "WHERE filial_id = :f AND produto_id = :p"
        ),
        {"f": filial_id, "p": produto_id},
    ).scalar_one_or_none()
    return Decimal(valor or 0)


def _movimentar(
    db: Session,
    *,
    filial_id: int,
    produto_id: int,
    quantidade: Decimal,
    tipo: str,
    origem: OrigemMov,
    documento_id: int,
) -> None:
    if tipo == "saida":
        r = db.execute(
            sa_text(
                "UPDATE produto_estoque SET saldo = saldo - :q, atualizado_em = now() "
                "WHERE filial_id = :f AND produto_id = :p AND saldo >= :q"
            ),
            {"q": quantidade, "f": filial_id, "p": produto_id},
        )
        if r.rowcount != 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Estoque insuficiente na origem para transferir.",
            )
    else:
        r = db.execute(
            sa_text(
                "UPDATE produto_estoque SET saldo = saldo + :q, atualizado_em = now() "
                "WHERE filial_id = :f AND produto_id = :p"
            ),
            {"q": quantidade, "f": filial_id, "p": produto_id},
        )
        if r.rowcount == 0:
            db.execute(
                sa_text(
                    "INSERT INTO produto_estoque (filial_id, produto_id, saldo) "
                    "VALUES (:f, :p, :q)"
                ),
                {"f": filial_id, "p": produto_id, "q": quantidade},
            )
    anterior = _saldo(db, filial_id, produto_id)
    posterior = (
        anterior - quantidade if tipo == "saida" else anterior + quantidade
    )
    db.add(
        MovimentoEstoque(
            filial_id=filial_id,
            produto_id=produto_id,
            tipo=TipoMovEstoque.SAIDA if tipo == "saida" else TipoMovEstoque.ENTRADA,
            origem=origem,
            documento_id=documento_id,
            quantidade=quantidade,
            saldo_anterior=anterior,
            saldo_posterior=posterior,
            motivo=f"Transferência {tipo} #{documento_id}",
        )
    )


def listar(
    db: Session, *, filial_id: int, limit: int = 50, offset: int = 0
) -> list[TransferenciaEstoque]:
    return (
        db.query(TransferenciaEstoque)
        .filter(
            (TransferenciaEstoque.filial_origem_id == filial_id)
            | (TransferenciaEstoque.filial_destino_id == filial_id)
        )
        .order_by(TransferenciaEstoque.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def registrar_saida(
    db: Session,
    *,
    filial_id: int,
    dados,
    usuario_id: int,
) -> TransferenciaEstoque:
    if dados.filial_destino_id == filial_id:
        raise HTTPException(400, "A filial de destino deve ser diferente da origem.")
    destino = db.get(Filial, dados.filial_destino_id)
    if destino is None or not destino.ativa:
        raise HTTPException(404, "Filial de destino não encontrada ou inativa.")

    numero = f"TR-{int(db.execute(sa_text('SELECT extract(epoch from now())')).scalar_one())}"
    doc = TransferenciaEstoque(
        numero=numero,
        filial_origem_id=filial_id,
        filial_destino_id=dados.filial_destino_id,
        produto_id=dados.produto_id,
        quantidade=dados.quantidade,
        estado=EstadoTransferencia.ENVIADA,
        observacoes=dados.observacoes,
        enviado_por=usuario_id,
    )
    db.add(doc)
    db.flush()
    _movimentar(
        db,
        filial_id=filial_id,
        produto_id=dados.produto_id,
        quantidade=dados.quantidade,
        tipo="saida",
        origem=OrigemMov.TRANSFERENCIA_SAIDA,
        documento_id=doc.id,
    )
    db.commit()
    db.refresh(doc)
    return doc


def confirmar_recebimento(
    db: Session, *, item_id: int, filial_id: int, usuario_id: int
) -> TransferenciaEstoque:
    doc = db.get(TransferenciaEstoque, item_id)
    if doc is None:
        raise HTTPException(404, "Transferência não encontrada.")
    if doc.filial_destino_id != filial_id:
        raise HTTPException(403, "Esta transferência é de outra filial.")
    if doc.estado != EstadoTransferencia.ENVIADA:
        raise HTTPException(409, "Transferência já recebida ou cancelada.")
    _movimentar(
        db,
        filial_id=filial_id,
        produto_id=doc.produto_id,
        quantidade=doc.quantidade,
        tipo="entrada",
        origem=OrigemMov.TRANSFERENCIA_ENTRADA,
        documento_id=doc.id,
    )
    doc.estado = EstadoTransferencia.RECEBIDA
    doc.recebido_por = usuario_id
    doc.recebido_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return doc


def cancelar(
    db: Session, *, item_id: int, filial_id: int, usuario_id: int
) -> TransferenciaEstoque:
    doc = db.get(TransferenciaEstoque, item_id)
    if doc is None:
        raise HTTPException(404, "Transferência não encontrada.")
    if doc.filial_origem_id != filial_id:
        raise HTTPException(403, "Esta transferência é de outra filial.")
    if doc.estado != EstadoTransferencia.ENVIADA:
        raise HTTPException(409, "Só transferências enviadas podem ser canceladas.")
    _movimentar(
        db,
        filial_id=filial_id,
        produto_id=doc.produto_id,
        quantidade=doc.quantidade,
        tipo="entrada",  # estorna a saída
        origem=OrigemMov.TRANSFERENCIA_SAIDA,
        documento_id=doc.id,
    )
    doc.estado = EstadoTransferencia.CANCELADA
    doc.cancelado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return doc
