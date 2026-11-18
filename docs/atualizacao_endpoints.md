# Chamada e atualização automática entre endpoints

Verificação feita em 18/11/2026 cobrindo categorias, produtos, serviços,
clientes e fluxo de caixa.

## Resultado da verificação

- **167 rotas** do backend vs **84 chamadas** do cliente desktop: todas
  correspondem (as 5 aparentes divergências são CRUD genérico `/{entidade}`
  e baixa dinâmica `financeiro/{tipo}`, ambos válidos).
- **Bug crítico corrigido na v0.5.5**: o Sync Agent usava `SET LOCAL ... = %s`,
  que falha no psycopg3; trocado por `set_config(..., true)` em `execute()`
  separada. Testes com Postgres real confirmam o ciclo completo.

## Melhorias de atualização automática

1. **Cache de catálogos com assinantes** (`core/catalogos.py`): `invalidar()`
   agora recarrega automaticamente todas as telas abertas que consomem
   `"produtos"`, `"categorias"`, `"clientes"`, `"funcionarios"` etc. Antes,
   uma categoria/cliente/produto editado só aparecia após novo login.
2. **Recarga ao trocar de tela** (`ui/tela_principal.py`): ao navegar para
   qualquer módulo (ou voltar ao Início), `recarregar()` é chamado em
   background — KPIs e listagens deixam de ficar parados a sessão inteira.
3. **Caixa sincronizado** (`venda_balcao.py`): após finalizar ou cancelar
   venda, `_verificar_caixa()` é chamado — o banner e o bloqueio refletem o
   movimento que o backend já lançou/estornou. `PaginaCaixa` também recarrega
   no `showEvent` ao voltar de outro módulo.
4. **DELETE gera evento de sync** (`crud_factory.py` + `crud.py`): soft delete
   de cliente/produto/fornecedor agora emite evento `DEL`, para a matriz e as
   filiais saberem da desativação. Antes só POST/PUT emitiam.

## Testes de regressão

`backend/tests/test_atualizacao_endpoints.py` cobre:
- cadastro de produto/categoria → evento `CRS`, atualização → `UPD`,
  exclusão → `DEL`, e a listagem lendo sempre do banco;
- cliente → evento para a fila de conflitos;
- venda → movimento no caixa + evento de sync.

Backend: **390 passed**. Desktop: **414 passed, 4 xfailed**.
