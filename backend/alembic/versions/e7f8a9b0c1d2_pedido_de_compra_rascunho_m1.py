"""pedido de compra em rascunho a partir da aprovacao (M1, PRD v3.0 §3.2.2 item 7)

Ao aprovar o orçamento (convertê-lo em OS), cada item de fornecedor com cotação
selecionada gera um **pedido de compra em rascunho** ao fornecedor escolhido:

- `pedido_compra.os_origem_id` → OS que o gerou (rastreabilidade);
- `pedido_compra_item.produto_id` passa a ser NULLABLE — serviço terceirizado
  não é um produto do catálogo (a descrição vive em `descricao_avulsa`);
- `os_item_cotacao.pedido_item_id` → item do pedido gerado a partir da cotação.

Aditivo e reversível: o down devolve a obrigatoriedade do produto (falha se
houver linhas de serviço terceirizado — documentado no docstring).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-10-26
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pedido de compra ligado à OS que o gerou (um por fornecedor; §3.2.2 item 7).
    op.add_column(
        "pedido_compra",
        sa.Column(
            "os_origem_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico.id"),
            nullable=True,
        ),
    )
    # Item de serviço terceirizado não tem produto no catálogo.
    op.alter_column("pedido_compra_item", "produto_id", nullable=True)
    # Cotação → item do pedido gerado (o VF vira o valor do pedido).
    op.add_column(
        "os_item_cotacao",
        sa.Column(
            "pedido_item_id",
            sa.BigInteger(),
            sa.ForeignKey("pedido_compra_item.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("os_item_cotacao", "pedido_item_id")
    op.drop_column("pedido_compra", "os_origem_id")
    # Devolve a obrigatoriedade: só é possível sem linhas de serviço terceirizado.
    op.alter_column("pedido_compra_item", "produto_id", nullable=False)
