-- Consolidação de LEITURA no Neon (PRD v3.3 §5.3/§5.6)
-- Aplicar DEPOIS de consolidacao_neon.sql, no banco consolidado.
-- Validado em 2026-11-17 na branch isolada `sync-agent-teste`.

-- Cadastros mestres publicados pela MATRIZ (RF-FL-03). Chave natural:
-- entidade ('mestre:produto', 'mestre:fornecedor') + código/cnpj.
CREATE TABLE IF NOT EXISTS consolidado.mestre (
    entidade text NOT NULL,
    chave text NOT NULL,
    versao bigint NOT NULL,
    payload jsonb NOT NULL,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entidade, chave)
);

-- A cada evento enviado, atualiza o mestre se a versão for maior
-- (a filial aplica por `versao`, RF-SY-05).
CREATE OR REPLACE FUNCTION consolidado.aplicar_mestre() RETURNS trigger AS $$
BEGIN
    IF NEW.entidade LIKE 'mestre:%' AND NULLIF(NEW.payload->>'chave', '') IS NOT NULL THEN
        INSERT INTO consolidado.mestre (entidade, chave, versao, payload, atualizado_em)
        VALUES (NEW.entidade, NEW.payload->>'chave', NEW.seq, NEW.payload, NEW.criado_em)
        ON CONFLICT (entidade, chave) DO UPDATE
            SET versao = EXCLUDED.versao,
                payload = EXCLUDED.payload,
                atualizado_em = EXCLUDED.atualizado_em
            WHERE EXCLUDED.versao > consolidado.mestre.versao;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_aplicar_mestre ON consolidado.evento_sync;
CREATE TRIGGER trg_aplicar_mestre
    AFTER INSERT ON consolidado.evento_sync
    FOR EACH ROW EXECUTE FUNCTION consolidado.aplicar_mestre();

-- Resolução da fila de conflitos de clientes (RF-FL-04): a Gerente da matriz
-- escolhe qual registro prevalece. A resolução também vive no Neon para que
-- todas as filiais a vejam.
CREATE TABLE IF NOT EXISTS consolidado.cliente_conflito_resolucao (
    documento text PRIMARY KEY,
    filial_escolhida bigint NOT NULL,
    uuid_escolhido text NOT NULL,
    resolvido_por bigint,
    payload jsonb,  -- dados do cliente escolhido, para a filial "descer"
    resolvido_em timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE consolidado.cliente_conflito_resolucao
    ADD COLUMN IF NOT EXISTS payload jsonb;

-- Relatórios consolidados derivam dos eventos imutáveis (RF-SY-04).
CREATE OR REPLACE VIEW consolidado.vw_vendas AS
SELECT DISTINCT ON (filial_id, entidade_id)
       filial_id,
       entidade_id AS venda_id,
       (payload->>'numero')::bigint AS numero,
       (payload->>'valor_total')::numeric(14,2) AS valor_total,
       payload->>'forma_pagamento' AS forma_pagamento,
       (payload->>'data_venda')::date AS data_venda,
       payload->>'status' AS status,
       criado_em
FROM consolidado.evento_sync
WHERE entidade = 'venda_balcao'
ORDER BY filial_id, entidade_id, seq DESC, criado_em DESC;
