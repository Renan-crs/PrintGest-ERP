"""Modelos do módulo Projetos (PRD Módulo Projetos — Quadro Kanban, §9).

O quadro deixa de ser uma visão sobre `/v1/os` e ganha entidade própria:

- `quadro` — um por filial.
- `quadro_lista` — colunas configuráveis, com `tipo` e mapeamento opcional para
  o status da O.S. (`status_os`). `usuario_dono_id` dá o nome às listas
  pessoais (PV3).
- `cartao` — unidade de trabalho, com vínculo **0..1** com uma O.S./Orçamento
  (`ordem_servico_id`, único — RN1). `versao` sustenta o controle otimista de
  edição (§10).
- `cartao_membro` — deriva a visibilidade do cartão (PV2/PV3/PV4). A
  visibilidade **nunca** é armazenada em `cartao`; ela é sempre recalculada a
  partir desta tabela.

As demais tabelas do PRD (etiqueta, checklist, anexo, comentário, atividade)
entram nas fases 2 e 3 — por isso `capa_anexo_id` ainda não existe aqui.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import Usuario
from app.models.enums import OrigemMembro, StatusOs, TipoLista, pg_enum

# Passo fracionário de ordenação (§10): posições são números racionais para
# inserir no meio sem renumerar a lista inteira. Ver `services/projetos_service`.
PASSO_FRACIONARIO = Decimal(1024)


class Quadro(Base):
    __tablename__ = "quadro"
    __table_args__ = (UniqueConstraint("filial_id", name="uq_quadro_filial"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    nome: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default="Projetos"
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    listas: Mapped[list["QuadroLista"]] = relationship(
        back_populates="quadro",
        cascade="all, delete-orphan",
        order_by="QuadroLista.posicao",
    )


class QuadroLista(Base):
    __tablename__ = "quadro_lista"
    __table_args__ = (Index("idx_quadro_lista_quadro", "quadro_id", "posicao"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    quadro_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quadro.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    posicao: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    tipo: Mapped[TipoLista] = mapped_column(
        pg_enum(TipoLista), nullable=False, server_default=TipoLista.LIVRE.value
    )
    status_os: Mapped[StatusOs | None] = mapped_column(pg_enum(StatusOs))
    usuario_dono_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id")
    )
    arquivada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    quadro: Mapped[Quadro] = relationship(back_populates="listas")
    usuario_dono: Mapped[Usuario | None] = relationship(
        foreign_keys=[usuario_dono_id]
    )


class Cartao(Base):
    __tablename__ = "cartao"
    __table_args__ = (
        Index("idx_cartao_lista", "lista_id", "posicao"),
        Index("idx_cartao_filial_arquivado", "filial_id", "arquivado"),
        # RN1: um cartão pertence a no máximo uma O.S./Orçamento (nulo = avulso).
        UniqueConstraint("ordem_servico_id", name="uq_cartao_ordem_servico"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    lista_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quadro_lista.id"), nullable=False
    )
    posicao: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    data_inicio: Mapped[date | None] = mapped_column(Date)
    data_entrega: Mapped[date | None] = mapped_column(Date)
    lembrete_min: Mapped[int | None] = mapped_column(Integer)
    concluido: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordem_servico_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
    )
    ultimo_responsavel_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    terceiro_fornecedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id")
    )
    terceiro_prazo: Mapped[date | None] = mapped_column(Date)
    terceiro_custo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    arquivado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # Controle otimista de edição (§10): texto com versão; conflito => 409.
    versao: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    lista: Mapped[QuadroLista] = relationship(foreign_keys=[lista_id])
    membros: Mapped[list["CartaoMembro"]] = relationship(
        back_populates="cartao",
        cascade="all, delete-orphan",
        foreign_keys="CartaoMembro.cartao_id",
    )


class CartaoMembro(Base):
    """Membro do cartão — fonte única da visibilidade (PV2, nunca armazenada)."""

    __tablename__ = "cartao_membro"
    __table_args__ = (
        UniqueConstraint("cartao_id", "usuario_id", name="uq_cartao_membro"),
        Index("idx_cartao_membro_usuario", "usuario_id"),
    )

    cartao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cartao.id", ondelete="CASCADE"), primary_key=True
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), primary_key=True
    )
    origem: Mapped[OrigemMembro] = mapped_column(
        pg_enum(OrigemMembro),
        nullable=False,
        server_default=OrigemMembro.MANUAL.value,
    )
    adicionado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    adicionado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    cartao: Mapped[Cartao] = relationship(back_populates="membros")
    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id])
