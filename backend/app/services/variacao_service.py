"""Geração automática de variantes (matriz de produtos).

Dado um produto "pai" (ex.: Carimbo) e uma lista de combinações de atributos
(tamanho, marca, cor), cria uma variante filha por combinação com:
- **SKU único** por filial, montado por `prefixo-TAM-MARCA-COR`;
- **uuid global** (RF-FL-02) para evitar conflitos de sincronização;
- estoque próprio (cada variante é tratada como produto acabado no PDV);
- código de barras único opcional.

O "estoque por consumo" de matéria-prima fica apenas na Produção/OS — aqui o
PDV continua leve, consultando diretamente o SKU no banco local.
"""

from __future__ import annotations

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cadastros import Produto, ProdutoEstoque
from app.models.enums import TipoProduto
from app.services import filial_service


def _slug(valor: str | None) -> str:
    texto = re.sub(r"[^A-Za-z0-9]", "", (valor or "").strip())
    return texto.upper()[:8]


def gerar(
    db: Session, *, filial_id: int, dados, usuario_id: int | None = None
) -> list[Produto]:
    pai = db.get(Produto, dados.produto_pai_id)
    if pai is None or pai.filial_id != filial_id:
        raise HTTPException(404, "Produto pai não encontrado nesta filial.")
    # Variação é produto acabado com estoque — serviço não pode ser pai.
    if pai.tipo != TipoProduto.PRODUTO:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Serviços não possuem variações com estoque.",
        )
    if not pai.ativo:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Não é possível gerar variações de um produto inativo.",
        )

    prefixo = _slug(dados.prefixo_sku or pai.codigo) or "VAR"
    criados: list[Produto] = []
    vistos: set[str] = set()
    try:
        for variacao in dados.variacoes:
            atributos = (
                variacao.tamanho, variacao.marca, variacao.cor
            )
            # Cada linha precisa identificar uma combinação real (spec PRD 3.2).
            if not any((a or "").strip() for a in atributos):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cada variação precisa de ao menos um atributo "
                    "(tamanho, marca ou cor).",
                )
            if variacao.codigo_barras:
                duplicado = (
                    db.query(Produto.id)
                    .filter(
                        Produto.filial_id == filial_id,
                        Produto.codigo_barras == variacao.codigo_barras,
                    )
                    .first()
                )
                if duplicado is not None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        detail="Código de barras já cadastrado nesta filial.",
                    )

            partes = [prefixo, *(_slug(a) for a in atributos)]
            sufixo = "-".join(p for p in partes if p)
            if sufixo in vistos:
                continue  # combinação duplicada no payload
            vistos.add(sufixo)
            sku = sufixo[:64]
            existe = (
                db.query(Produto)
                .filter(Produto.filial_id == filial_id, Produto.sku == sku)
                .first()
            )
            if existe is not None:
                # Reativa uma filha excluída e garante sua posição de estoque
                # (antes a idempotência ignorava a exclusão para sempre).
                if not existe.ativo:
                    existe.ativo = True
                    if (
                        db.query(ProdutoEstoque.id)
                        .filter(
                            ProdutoEstoque.filial_id == filial_id,
                            ProdutoEstoque.produto_id == existe.id,
                        )
                        .first() is None
                    ):
                        db.add(
                            ProdutoEstoque(
                                filial_id=filial_id, produto_id=existe.id, saldo=0
                            )
                        )
                    # Reativação também replica (antes ficava sem evento).
                    filial_service.registrar_evento(
                        db,
                        filial_id=filial_id,
                        entidade="mestre:produto",
                        entidade_id=existe.id,
                        operacao="UPD",
                        payload={
                            "chave": existe.sku,
                            "id": existe.id,
                            "nome": existe.nome,
                            "preco_venda": str(existe.preco_venda),
                            "uuid": existe.uuid,
                            "operacao": "reativacao",
                            "gerado_por": usuario_id,
                        },
                    )
                continue  # idempotente

            rotulo = " ".join(p for p in atributos if p)
            # `codigo` é único por filial: mais entropia e verificação explícita.
            while True:
                codigo = f"{sku}-{uuid.uuid4().hex[:8]}"[:30]
                if (
                    db.query(Produto.id)
                    .filter(Produto.filial_id == filial_id, Produto.codigo == codigo)
                    .first() is None
                ):
                    break
            filha = Produto(
                filial_id=filial_id,
                categoria_id=pai.categoria_id,
                codigo=codigo,
                sku=sku,
                uuid=str(uuid.uuid4()),
                produto_pai_id=pai.id,
                atrib_tamanho=variacao.tamanho,
                atrib_marca=variacao.marca,
                atrib_cor=variacao.cor,
                codigo_barras=variacao.codigo_barras,
                nome=f"{pai.nome} {rotulo}".strip()[:160],
                descricao=pai.descricao,
                tipo=TipoProduto.PRODUTO,  # filha é sempre produto acabado
                unidade=pai.unidade,
                controla_estoque=True,
                preco_custo=pai.preco_custo,
                preco_venda=(
                    variacao.preco_venda
                    if variacao.preco_venda is not None
                    else pai.preco_venda
                ),
                estoque_minimo=pai.estoque_minimo,
            )
            db.add(filha)
            db.flush()
            db.add(
                ProdutoEstoque(
                    filial_id=filial_id, produto_id=filha.id, saldo=0
                )
            )
            # Cada variante é um cadastro mestre (matriz → filiais).
            filial_service.registrar_evento(
                db,
                filial_id=filial_id,
                entidade="mestre:produto",
                entidade_id=filha.id,
                operacao="CRS",
                payload={
                    "chave": sku,
                    "id": filha.id,
                    "nome": filha.nome,
                    "preco_venda": str(filha.preco_venda),
                    "uuid": filha.uuid,
                    "gerado_por": usuario_id,
                },
            )
            criados.append(filha)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Conflito de código/SKU ao gerar variações. Tente novamente.",
        ) from exc
    return criados


def buscar_por_sku(
    db: Session, *, filial_id: int, termo: str
) -> Produto | None:
    """Leitura direta por SKU/uuid/código de barras — sem navegar variações."""
    busca = (termo or "").strip()
    if not busca:
        return None
    return (
        db.query(Produto)
        .filter(
            Produto.filial_id == filial_id,
            Produto.ativo.is_(True),
            Produto.tipo == TipoProduto.PRODUTO,
            (
                (Produto.sku == busca)
                | (Produto.uuid == busca)
                | (Produto.codigo_barras == busca)
                | (Produto.codigo == busca)
            ),
        )
        .first()
    )
