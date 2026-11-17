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

## Limites atuais (próxima fase)

- A tabela consolidada guarda os **eventos** (fonte da verdade por dono). A
  **descida de cadastros mestres** e os **relatórios consolidados** ainda não
  consomem essa tabela — são o próximo passo (RF-SY-05/06, RF-FL-04).
- A fila de conflitos de clientes (desduplicação por CPF/CNPJ) depende dessa
  consolidação e também fica para a próxima fase.
