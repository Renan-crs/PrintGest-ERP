# Sync Agent — consolidação entre filiais no Neon (PRD v3.3 §5)

## O que foi implementado

- **Outbox local** (`evento_sync`): toda venda de balcão (criação/cancelamento)
  e alteração de filial gera um evento **na mesma transação** (RF-SY-01).
  `uuid` é a chave de idempotência e `seq` ordena a fila por filial.
- **Sync Agent** (`app/services/sync_service.py`): loop em background no
  Local API Service que lê pendentes em lotes, envia ao Neon com
  `SET LOCAL app.filial_id` + `ON CONFLICT (uuid) DO NOTHING`, e marca como
  enviados **somente** os aceitos. Sem internet os eventos acumulam e o envio
  retoma ao reconectar, sem duplicar.
- **Backoff** 60/300/900/3600 s com jitter de ±20% (já existente no RedGest,
  reusado aqui).
- **URL por filial no cofre DPAPI** (`cofre_sync.py`), nunca em `.env`, banco,
  log ou backup.

## Provisionar o Neon (UMA vez)

1. Aplicar `backend/sql/consolidacao_neon.sql` no **banco consolidado**:
   cria schema `consolidado`, tabela `evento_sync` e policy RLS por filial.
2. Para **cada filial**, criar um role de menor privilégio:
   `create_postgres_role(name='printgest_sync_filial_<id>', access='read_write',
   database_name='<db>', schemas=['consolidado'])`.
   O role só tem INSERT/UPDATE/DELETE em `consolidado` — nunca `neondb_owner`.
3. No desktop, **Configurações > Filiais** (ou `PUT /v1/plataforma/sync/config`)
   registrar a URL desse role: `postgresql://<role>:<senha>@<host>/<db>`.
   A senha é cifrada no cofre e **nunca** é devolvida pela API (só máscara).
4. Validar com `GET /v1/plataforma/sync/status` e `POST .../sync/executar`.

## Validação feita

Schema + RLS aplicados em **branch isolada** (`sync-agent-teste`, projeto
`printg`) — nunca em produção. Com `app.filial_id = 1`, a policy permite a
linha da filial 1 e bloqueia a da filial 2; `uuid` impediu duplicata no
reenvio. Testes Python com conexão psycopg mockada: nenhum acesso real ao Neon.

## Consolidação de leitura (implementada)

- **Mestres**: `consolidado.mestre` (tabela + trigger em
  `backend/sql/consolidacao_leitura.sql`) guarda produtos/fornecedores
  publicados pela matriz com `versao`. A filial desce por `versao > cursor`
  (`sinc_estado`) e aplica no banco local (RF-SY-05) — sem alterar orçamentos
  já emitidos (RF-SY-06). Clientes, produtos e fornecedores em item geram
  evento de sync **na mesma transação** (RF-SY-01).
- **Relatórios**: view `consolidado.vw_vendas` → `GET .../consolidacao/relatorio`,
  com faturamento por filial e rótulo de defasagem (§5.6).
- **Conflitos de clientes**: duplicatas por CPF/CNPJ entre filiais aparecem em
  `GET .../consolidacao/conflitos`; a Gerente da matriz resolve com
  `POST .../conflitos/resolver` (RF-FL-04).
- Telas Admin: **Configurações > Consolidação** e **Filiais**.

Tudo validado em branch isolada (`sync-agent-teste`) e com psycopg mockado nos
testes — nenhum acesso real ao Neon nos testes automatizados.

## Publicação e desduplicação (concluído)

- **Mestres**: produtos e fornecedores criaram evento `mestre:*`
  **automaticamente na mesma transação** (RF-SY-01) — mas **somente quando a
  filial tem papel MATRIZ**. Filial com papel `FILIAL` recebe os mestres e não
  publica (RF-FL-03). Papel nulo = legado/single-tenant, publica como antes.
- **Conflitos**: ao resolver, a Gerente escolhe o `uuid` do cliente vencedor;
  o backend lê o payload dele no outbox e grava na resolução (coluna `payload`).
  As filiais executam **`POST .../consolidacao/conflitos/descer`** (botão
  *Descer resoluções* na tela Consolidação): o cliente local é **renomeado**
  com os dados do escolhido e duplicatas são **inativadas (soft delete)** —
  nenhum dado é apagado. Idempotente por `sinc_estado` (`resolucao:<doc>`).

## Ciclo completo

O `_loop_sync_agent` executa, **por filial e por ciclo**: subida do outbox →
descida de mestres → descida de resoluções de conflito. Cada etapa é isolada
por `try/except`: falha de uma não impede as outras nem derruba o serviço.
Todas são idempotentes (`uuid`/`sinc_estado`), então repetir o ciclo é seguro.

A ação manual *Descer resoluções* na tela continua disponível para aplicar
imediatamente sem esperar o próximo ciclo.
