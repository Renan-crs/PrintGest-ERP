# Migration `e5f6a7b8c9d0` — regras de preço com vigência (Fase V1)

**Status:** **aplicada ao Neon de produção em 24/11/2026**, com autorização
explícita do usuário e backup prévio em branch. Head do Alembic em produção:
`e5f6a7b8c9d0`. Backup: `br-wispy-bread-b5vzu4hf`
(`backup-pre-migration-regras-preco-20261124`, LSN `0/39488F0`).

## O que a migration faz

Operação **aditiva** — nenhuma coluna existente é alterada, renomeada ou
removida e nenhum dado é apagado:

| Objeto | Ação |
|---|---|
| `tabela_preco` | tabela nova (id, uuid, `filial_id`, `cliente_id`, nome, `padrao`, `ativo`, timestamps) |
| `regra_preco` | tabela nova (id, uuid, tabela, produto, `preco_base`, `faixas`/`modificadores` JSONB, `minimo`, `modo_faixa`, vigência, prioridade, auditoria) |
| `venda_balcao_item.preco_snapshot` | coluna JSONB **anulável** |
| `ordem_servico_item.preco_snapshot` | coluna JSONB **anulável** |

Índices únicos parciais por `uuid` (idempotência de sincronização) e índice de
vigência para a consulta de precedência. Constraints: tabela padrão sem
cliente, `vigencia_fim > vigencia_inicio`, `preco_base >= 0`, `prioridade >= 0`.

**Isolamento:** toda tabela pertence a uma `filial_id` — não existe tabela
global que atravesse inquilinos.

## Compatibilidade

- Registros antigos ficam com `preco_snapshot = NULL` e o sistema continua
  usando o comportamento legado (`valor_unitario` enviado pelo cliente).
- Nenhuma regra é criada automaticamente: o preço só passa a ser calculado no
  servidor depois que uma regra vigente for cadastrada em
  `POST /v1/precificacao/regras`.
- `downgrade()` remove apenas os objetos criados — não toca em dados de preço
  já existentes nas tabelas antigas.

## Antes de aplicar em produção

1. **Backup:** criar branch no Neon (snapshots podem estar no limite):
   `backup-pre-migration-regras-preco-20261124`.
2. **Pré-checagem** (somente leitura): confirmar que não há tabelas/regras com
   o mesmo nome e que o head atual é `d4e5f6a7b8c9`.
3. **Aplicar** com `DATABASE_URL` apontando para a branch de produção:

   ```powershell
   $env:PRINTGEST_DATABASE_URL = "<url-neon-producao>"
   backend\.venv\Scripts\python.exe -m alembic upgrade e5f6a7b8c9d0
   ```

4. **Verificar:** `\dt tabela_preco`, `\dt regra_preco`, e as duas colunas
   `preco_snapshot`; em seguida executar um smoke test de venda sem regra
   (deve manter o preço legado).

### Resultado da aplicação (24/11/2026)

Aplicação concluída em uma transação com as 9 instruções do arquivo de
migration e a atualização de `alembic_version`. Verificação pós-aplicação:

- `alembic_version` = `e5f6a7b8c9d0`;
- `tabela_preco` e `regra_preco` presentes em `public`;
- `preco_snapshot` (jsonb) presente em `venda_balcao_item` e
  `ordem_servico_item`;
- nenhum dado existente alterado — as novas colunas começam nulas e o preço
  legado continua valendo até uma regra ser cadastrada.

## Reversão

```powershell
$env:PRINTGEST_DATABASE_URL = "<url-neon-producao>"
backend\.venv\Scripts\python.exe -m alembic downgrade d4e5f6a7b8c9
```

A reversão descarta as regras cadastradas após a aplicação — por isso o backup
em branch é obrigatório antes de executar.
