# Migration `f6a7b8c9d0e1` — fichas de consumo (Fase V2)

**Status:** **aplicada ao Neon de produção em 25/11/2026**, com autorização
explícita do usuário e backup prévio em branch. Head do Alembic em produção:
`f6a7b8c9d0e1`. Backup: `br-purple-dust-b5d7t5rm`
(`backup-pre-migration-fichas-consumo-20261125`, LSN `0/3A86270`).

## O que a migration faz

Operação **aditiva** — cria apenas duas tabelas:

| Objeto | Finalidade |
|---|---|
| `ficha_consumo` | Receita de produção por produto/insumo, com vigência, perda percentual e custo de processo |
| `os_item_consumo` | Consumo previsto e real por item de OS, com `baixado_em` como guarda de idempotência |

Nenhuma coluna existente é alterada, nenhuma constraint de `produto` ou
`ordem_servico_item` é modificada e nenhum dado é apagado.

**Reaproveitamento:** o insumo é um `produto` com `controla_estoque=true`; seu
saldo está em `produto_estoque` e a baixa real grava `movimento_estoque` com
`OrigemMov.ORDEM_SERVICO`. Não há novo kardex nem custo médio ponderado nesta
entrega.

## Compatibilidade

- Itens avulsos, orçamentos e itens de fornecedor não geram consumo: a ficha
  só é considerada quando o item tem `produto_id` e há ficha vigente.
- `PATCH /v1/os/{id}/status` continua com o mesmo contrato; o consumo previsto
  é gravado ao entrar em produção, sem exigir estoque nem alterar o gate de
  arte.
- A baixa real só acontece no endpoint novo, explícito:
  `POST /v1/producao/os/{os_id}/itens/{item_id}/baixar-consumo`.

## Antes de aplicar em produção

1. Backup: branch `backup-pre-migration-fichas-consumo-20261124` (snapshots
   podem estar no limite).
2. Confirmar head atual `e5f6a7b8c9d0`.
3. Aplicar com `DATABASE_URL` da produção:

   ```powershell
   $env:PRINTGEST_DATABASE_URL = "<url-neon-producao>"
   backend\.venv\Scripts\python.exe -m alembic upgrade f6a7b8c9d0e1
   ```

4. Verificar `ficha_consumo`, `os_item_consumo` e seus índices.

### Resultado da aplicação (25/11/2026)

Aplicação concluída em uma transação com as 6 instruções do arquivo de
migration e a atualização de `alembic_version`. Verificação pós-aplicação:

- `alembic_version` = `f6a7b8c9d0e1`;
- `ficha_consumo` e `os_item_consumo` presentes em `public`;
- índices `uq_ficha_consumo_uuid`, `idx_ficha_consumo_vigencia`,
  `uq_os_item_consumo` e `idx_os_item_consumo_filial` presentes;
- nenhum dado existente alterado — as tabelas novas começam vazias e o fluxo
  legado permanece intacto até uma ficha ser cadastrada.

## Reversão

```powershell
backend\.venv\Scripts\python.exe -m alembic downgrade e5f6a7b8c9d0
```

Descarta as fichas e os consumos cadastrados após a aplicação — exige o backup.
