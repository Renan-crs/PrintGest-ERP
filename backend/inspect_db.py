import os

from sqlalchemy import create_engine, inspect

# Usar .env.local se existir
env_local_path = os.path.join(os.path.dirname(__file__), ".env.local")
if os.path.exists(env_local_path):
    with open(env_local_path) as f:
        for line in f:
            if line.startswith("DATABASE_URL="):
                db_url = line.strip().split("=", 1)[1].strip('"')
                break

if "db_url" not in locals():
    db_url = os.getenv("DATABASE_URL") or os.getenv("PRINTGEST_DATABASE_URL")

engine = create_engine(db_url)

inspector = inspect(engine)

print("=" * 60)
print("ESQUEMA DO BANCO DE DADOS - PrintGest ERP")
print("=" * 60)

# Listar todas as tabelas
tables = inspector.get_table_names()
print("Tabelas encontradas:", len(tables))
print()

# Mostrar informações de cada tabela
for table in sorted(tables):
    columns = inspector.get_columns(table)
    pk = inspector.get_pk_constraint(table)
    fks = inspector.get_foreign_keys(table)

    print("Tabela:", table)
    print("  Colunas:", len(columns))
    if pk.get("constrained_columns"):
        pk_cols = ", ".join(pk["constrained_columns"])
        print("  PK:", pk_cols)
    for fk in fks:
        cols = fk.get("constrained_columns", [])
        ref = fk.get("referred_table", "")
        fk_cols = ", ".join(cols)
        print("  FK ->", ref, ":", fk_cols)
    print()

# Mostrar resumo por schema
print("=" * 60)
print("RESUMO DAS ENTIDADES PRINCIPAIS")
print("=" * 60)

entity_counts = {
    "Usuários e Autenticação": [
        "usuario",
        "funcionario",
        "perfil",
        "entitlement",
        "licenca",
        "modulo",
        "entitlements_modulos",
    ],
    "Clientes e Cadastros": ["cliente", "cidade", "estado", "pais"],
    "Produtos e Serviços": [
        "produto",
        "servico",
        "categoria",
        "unidade_medida",
        "tipo_produto",
    ],
    "Movimento": ["orcamento", "ordem_servico", "item_os", "orcamento_item"],
    "Estoque": ["estoque", "item_estoque", "movimento_estoque", "estoque_lote"],
    "Financeiro": [
        "conta_pagar",
        "conta_receber",
        "parcela",
        "sala_conta",
        "tipo_conta",
        "plano_conta",
        "caixa",
    ],
    "Fornecedores": [
        "fornecedor",
        "cotacao",
        "cotacao_proposta",
        "pedido_compra",
        "item_pedido_compra",
    ],
    "Projetos": [
        "projeto",
        "quadro",
        "quadro_lista",
        "cartao",
        "cartao_membro",
        "cartao_checklist",
        "cartao_checklist_item",
        "atividade",
    ],
    "Arte": ["arte_arquivo", "arte_versao", "arte_aprovacao", "link_publico"],
    "Fiscal": [
        "documento_fiscal",
        "nota_fiscal",
        "tipo_fiscal",
        "modelo_fiscal",
        "status_fiscal",
    ],
    "Agendamento": ["agendamento", "evento"],
    "Configurações": ["parametro", "preco_parametro", "preco_faixa", "preco_cliente"],
}

for category, expected_tables in entity_counts.items():
    found = [t for t in expected_tables if t in tables]
    if found:
        print("{}: {} {}".format(category, len(found), ", ".join(found)))
