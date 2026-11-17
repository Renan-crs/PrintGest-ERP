-- Consolidação entre filiais no Neon (PRD v3.3 §5.4/§5.5)
-- Aplicar no BANCO CONSOLIDADO (projeto Neon), nunca no banco operacional local.
-- Validado em 2026-11-17 na branch isolada `sync-agent-teste` do projeto printg.

CREATE SCHEMA IF NOT EXISTS consolidado;

CREATE TABLE IF NOT EXISTS consolidado.evento_sync (
    uuid text PRIMARY KEY,
    filial_id bigint NOT NULL,
    entidade text NOT NULL,
    entidade_id bigint,
    operacao text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    seq bigint NOT NULL,
    criado_em timestamptz NOT NULL,
    recebido_em timestamptz NOT NULL DEFAULT now()
);

-- RLS: cada filial vê/escreve só suas linhas. O Sync Agent define
-- `SET LOCAL app.filial_id = <id>` antes de cada INSERT (RF-SC-02).
ALTER TABLE consolidado.evento_sync ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS evento_sync_filial ON consolidado.evento_sync;
CREATE POLICY evento_sync_filial ON consolidado.evento_sync
    USING (filial_id = NULLIF(current_setting('app.filial_id', true), '')::bigint)
    WITH CHECK (filial_id = NULLIF(current_setting('app.filial_id', true), '')::bigint);

-- Por filial, criar um role de menor privilégio (RF-SC-03). No Neon:
--   create_postgres_role(
--     name='printgest_sync_filial_<id>', access='read_write',
--     database_name='<db consolidado>', schemas=['consolidado'])
-- A URL de conexão desse role vai para o cofre DPAPI por filial:
--   PUT /v1/plataforma/sync/config  {"url": "postgresql://..."}
-- A senha NUNCA vai para .env, banco, log ou backup.
