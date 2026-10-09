"""reforco integridade: FKs, CHECKs, UNIQUEs e indices de nome

Revision ID: f1a09c3b2d84
Revises: ae9f00b5a9a1
Create Date: 2026-09-21

Aplica as correções de integridade apontadas na revisão de schema:
  1) UNIQUE chave_acesso e (modelo, numero, serie) em documento_fiscal
  2) FK real venda_balcao.documento_fiscal_id -> documento_fiscal
  3) UNIQUE parcial 'caixa aberto' + CHECKs de valores nÃ£o-negativos/consistentes
  4) Ìndices de nome em usuario/funcionario/fornecedor
  5) Multi-filial: produto_categoria e plano_contas com filial_id NOT NULL + UNIQUE
  6) CHECKs de recebimento <= pedido e horário de agenda
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a09c3b2d84"
down_revision: Union[str, None] = "ae9f00b5a9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1) documento_fiscal: UNIQUEs fiscais (colunas NULLáveis aceitam N linhas NULL) ---
    op.drop_index("idx_df_chave", table_name="documento_fiscal")
    op.create_unique_constraint(
        "uq_df_chave_acesso", "documento_fiscal", ["chave_acesso"]
    )
    op.create_unique_constraint(
        "uq_df_modelo_numero_serie", "documento_fiscal", ["modelo", "numero", "serie"]
    )

    # --- 2) venda_balcao: FK real para o documento fiscal ---
    op.create_foreign_key(
        "venda_balcao_documento_fiscal_id_fkey",
        "venda_balcao",
        "documento_fiscal",
        ["documento_fiscal_id"],
        ["id"],
    )

    # --- 3) CHECKs de valores em venda_balcao ---
    op.create_check_constraint(
        "ck_venda_valores_nao_negativos",
        "venda_balcao",
        "desconto >= 0 AND valor_itens >= 0 AND valor_total >= 0",
    )
    op.create_check_constraint(
        "ck_venda_valor_consistente",
        "venda_balcao",
        "valor_itens - desconto = valor_total",
    )
    op.create_check_constraint("ck_venda_parcelas", "venda_balcao", "parcelas >= 1")

    op.create_check_constraint(
        "ck_venda_item_qtd_positiva", "venda_balcao_item", "quantidade > 0"
    )
    op.create_check_constraint(
        "ck_venda_item_valores_nao_negativos",
        "venda_balcao_item",
        "valor_unitario >= 0 AND desconto >= 0 AND valor_total >= 0",
    )

    op.create_check_constraint(
        "ck_os_valores_nao_negativos",
        "ordem_servico",
        "desconto >= 0 AND valor_itens >= 0 AND valor_total >= 0",
    )
    op.create_check_constraint(
        "ck_os_valor_consistente",
        "ordem_servico",
        "valor_itens - desconto = valor_total",
    )
    op.create_check_constraint(
        "ck_os_item_qtd_positiva", "ordem_servico_item", "quantidade > 0"
    )
    op.create_check_constraint(
        "ck_os_item_valores_nao_negativos",
        "ordem_servico_item",
        "valor_unitario >= 0 AND desconto >= 0 AND valor_total >= 0",
    )

    op.create_check_constraint(
        "ck_pedido_valor_total", "pedido_compra", "valor_total >= 0"
    )
    op.create_check_constraint(
        "ck_pedido_item_qtd_positiva", "pedido_compra_item", "quantidade > 0"
    )
    op.create_check_constraint(
        "ck_pedido_item_qtd_recebida",
        "pedido_compra_item",
        "quantidade_recebida BETWEEN 0 AND quantidade",
    )
    op.create_check_constraint(
        "ck_pedido_item_valores_nao_negativos",
        "pedido_compra_item",
        "valor_unitario >= 0 AND valor_total >= 0",
    )

    op.create_check_constraint(
        "ck_agendamento_horario",
        "agendamento",
        "data_hora_fim IS NULL OR data_hora_fim > data_hora_inicio",
    )

    # --- 3) caixa: caixa aberto Ãºnico por usuÃ¡rio/filial + valor >= 0 ---
    op.create_check_constraint("ck_caixa_valor_abertura", "caixa", "valor_abertura >= 0")
    op.create_index(
        "uq_caixa_aberto_filial_usuario",
        "caixa",
        ["filial_id", "usuario_id"],
        unique=True,
        postgresql_where=sa.text("status = 'aberto'"),
    )

    op.create_check_constraint("ck_movcaixa_valor", "movimento_caixa", "valor >= 0")

    op.create_check_constraint(
        "ck_cr_valores_nao_negativos", "conta_receber", "valor >= 0 AND valor_pago >= 0"
    )
    op.create_check_constraint(
        "ck_cr_parcelas", "conta_receber", "parcela >= 1 AND total_parcelas >= 1"
    )
    op.create_check_constraint(
        "ck_cp_valores_nao_negativos", "conta_pagar", "valor >= 0 AND valor_pago >= 0"
    )
    op.create_check_constraint(
        "ck_cp_parcelas", "conta_pagar", "parcela >= 1 AND total_parcelas >= 1"
    )

    op.create_check_constraint(
        "ck_produto_precos", "produto", "preco_custo >= 0 AND preco_venda >= 0"
    )
    op.create_check_constraint(
        "ck_produto_estoque_minimo", "produto", "estoque_minimo >= 0"
    )
    op.create_check_constraint(
        "ck_funcionario_comissao", "funcionario", "comissao_pct BETWEEN 0 AND 100"
    )

    # --- 4) Ã­ndices de busca por nome ---
    op.create_index("idx_usuario_nome", "usuario", ["nome"], unique=False)
    op.create_index("idx_funcionario_nome", "funcionario", ["nome"], unique=False)
    op.create_index("idx_fornecedor_nome", "fornecedor", ["nome_razao"], unique=False)

    # --- 5) multi-filial: categoria por filial + filial_id obrigatório ---
    op.drop_constraint("produto_categoria_nome_key", "produto_categoria", type_="unique")
    # Backfill antes do NOT NULL: bancos já populados podem ter linhas sem filial
    # (P12 — sem isto o upgrade falharia). Assume a filial de menor id (MVP).
    op.execute(
        "UPDATE produto_categoria SET filial_id = "
        "COALESCE((SELECT id FROM filial ORDER BY id LIMIT 1), 1) "
        "WHERE filial_id IS NULL"
    )
    op.alter_column("produto_categoria", "filial_id", existing_type=sa.BigInteger(), nullable=False)
    op.create_unique_constraint(
        "uq_produto_categoria_filial_nome", "produto_categoria", ["filial_id", "nome"]
    )
    op.execute(
        "UPDATE plano_contas SET filial_id = "
        "COALESCE((SELECT id FROM filial ORDER BY id LIMIT 1), 1) "
        "WHERE filial_id IS NULL"
    )
    op.alter_column("plano_contas", "filial_id", existing_type=sa.BigInteger(), nullable=False)


def downgrade() -> None:
    # --- 5) reverter multi-filial ---
    op.alter_column("plano_contas", "filial_id", existing_type=sa.BigInteger(), nullable=True)
    op.drop_constraint(
        "uq_produto_categoria_filial_nome", "produto_categoria", type_="unique"
    )
    op.alter_column("produto_categoria", "filial_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_unique_constraint("produto_categoria_nome_key", "produto_categoria", ["nome"])

    # --- 4) dropar Ã­ndices de nome ---
    op.drop_index("idx_fornecedor_nome", table_name="fornecedor")
    op.drop_index("idx_funcionario_nome", table_name="funcionario")
    op.drop_index("idx_usuario_nome", table_name="usuario")

    op.drop_constraint("ck_funcionario_comissao", "funcionario", type_="check")
    op.drop_constraint("ck_produto_estoque_minimo", "produto", type_="check")
    op.drop_constraint("ck_produto_precos", "produto", type_="check")
    op.drop_constraint("ck_cp_parcelas", "conta_pagar", type_="check")
    op.drop_constraint("ck_cp_valores_nao_negativos", "conta_pagar", type_="check")
    op.drop_constraint("ck_cr_parcelas", "conta_receber", type_="check")
    op.drop_constraint("ck_cr_valores_nao_negativos", "conta_receber", type_="check")
    op.drop_constraint("ck_movcaixa_valor", "movimento_caixa", type_="check")
    op.drop_index("uq_caixa_aberto_filial_usuario", table_name="caixa")
    op.drop_constraint("ck_caixa_valor_abertura", "caixa", type_="check")

    op.drop_constraint("ck_agendamento_horario", "agendamento", type_="check")
    op.drop_constraint(
        "ck_pedido_item_valores_nao_negativos", "pedido_compra_item", type_="check"
    )
    op.drop_constraint("ck_pedido_item_qtd_recebida", "pedido_compra_item", type_="check")
    op.drop_constraint("ck_pedido_item_qtd_positiva", "pedido_compra_item", type_="check")
    op.drop_constraint("ck_pedido_valor_total", "pedido_compra", type_="check")
    op.drop_constraint(
        "ck_os_item_valores_nao_negativos", "ordem_servico_item", type_="check"
    )
    op.drop_constraint("ck_os_item_qtd_positiva", "ordem_servico_item", type_="check")
    op.drop_constraint("ck_os_valor_consistente", "ordem_servico", type_="check")
    op.drop_constraint(
        "ck_os_valores_nao_negativos", "ordem_servico", type_="check"
    )
    op.drop_constraint(
        "ck_venda_item_valores_nao_negativos", "venda_balcao_item", type_="check"
    )
    op.drop_constraint("ck_venda_item_qtd_positiva", "venda_balcao_item", type_="check")
    op.drop_constraint("ck_venda_parcelas", "venda_balcao", type_="check")
    op.drop_constraint("ck_venda_valor_consistente", "venda_balcao", type_="check")
    op.drop_constraint("ck_venda_valores_nao_negativos", "venda_balcao", type_="check")

    # --- 2) reverter FK venda_balcao.documento_fiscal_id ---
    op.drop_constraint(
        "venda_balcao_documento_fiscal_id_fkey", "venda_balcao", type_="foreignkey"
    )

    # --- 1) reverter UNIQUEs fiscais ---
    op.drop_constraint("uq_df_modelo_numero_serie", "documento_fiscal", type_="unique")
    op.drop_constraint("uq_df_chave_acesso", "documento_fiscal", type_="unique")
    op.create_index("idx_df_chave", "documento_fiscal", ["chave_acesso"], unique=False)