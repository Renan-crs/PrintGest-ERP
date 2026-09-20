-- ============================================================================
-- PrintGest ERP — Schema de Referência (PostgreSQL 15+)
-- Fase 0 · Baseline · 2026-09-20
-- Fonte: PRD v2.0 §4 e docs/telas_e_fluxos.md
--
-- Convenções:
--   * PK: BIGSERIAL "id"
--   * Timestamps: TIMESTAMPTZ DEFAULT now()  (autoupdate via trigger set_updated_at)
--   * Money: NUMERIC(14,2)   Quantidade: NUMERIC(12,3)   Percentual: NUMERIC(6,3)
--   * Toda tabela operacional tem filial_id (D5 — 1 filial hoje, modelo pronto p/ N)
--   * ENUM nativos do PostgreSQL (sem extensão); app/backup manipulam via texto
--   * Deleções: soft delete via flag ativo/status/cancelado (auditoria)
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Função utilitária p/ atualização automática de updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ===========================================================================
-- ENUMS
-- ===========================================================================
CREATE TYPE nivel_acesso     AS ENUM ('admin', 'gerente', 'operador', 'caixa');
CREATE TYPE tipo_pessoa      AS ENUM ('pf', 'pj');
CREATE TYPE tipo_produto     AS ENUM ('produto', 'servico');
CREATE TYPE tipo_mov_estoque AS ENUM ('entrada', 'saida', 'ajuste');
CREATE TYPE origem_mov       AS ENUM ('venda_balcao', 'ordem_servico', 'pedido_compra', 'ajuste_manual');
CREATE TYPE tipo_os          AS ENUM ('orcamento', 'os');
CREATE TYPE status_os        AS ENUM ('aberto', 'aprovado', 'producao', 'pronta', 'entregue', 'cancelado', 'convertido');
CREATE TYPE status_venda     AS ENUM ('ok', 'cancelado');
CREATE TYPE status_pedido    AS ENUM ('aberto', 'recebido', 'cancelado');
CREATE TYPE status_agenda    AS ENUM ('agendado', 'concluido', 'cancelado');
CREATE TYPE tipo_agenda      AS ENUM ('producao', 'entrega');
CREATE TYPE tipo_plano_conta AS ENUM ('receita', 'despesa');
CREATE TYPE status_conta     AS ENUM ('aberta', 'paga', 'cancelada');
CREATE TYPE status_caixa     AS ENUM ('aberto', 'fechado');
CREATE TYPE tipo_mov_caixa   AS ENUM ('entrada', 'saida', 'sangria', 'suprimento');
CREATE TYPE forma_pagamento  AS ENUM ('dinheiro', 'cartao_credito', 'cartao_debito', 'pix', 'boleto', 'fiado');
CREATE TYPE modelo_fiscal    AS ENUM ('nfe', 'nfce');
CREATE TYPE status_fiscal    AS ENUM ('rascunho', 'processando', 'autorizado', 'rejeitado', 'cancelado', 'contingenciado');

-- ===========================================================================
-- SEQUÊNCIAS DE NUMERAÇÃO (sequência global; exibição por filial no app)
-- ===========================================================================
CREATE SEQUENCE seq_os_numero        START 1;
CREATE SEQUENCE seq_venda_numero     START 1;
CREATE SEQUENCE seq_pedido_numero    START 1;

-- ===========================================================================
-- EMPRESA / FILIAL
-- ===========================================================================
CREATE TABLE empresa (
    id                  BIGSERIAL PRIMARY KEY,
    razao_social        VARCHAR(200)    NOT NULL,
    nome_fantasia       VARCHAR(120),
    cnpj                CHAR(14)        NOT NULL UNIQUE,
    inscricao_estadual  VARCHAR(20),
    inscricao_municipal VARCHAR(20),
    regime_tributario   VARCHAR(60)     DEFAULT 'Simples Nacional',
    ambiente_fiscal     CHAR(1)         NOT NULL DEFAULT 'h' CHECK (ambiente_fiscal IN ('h', 'p')),
    cnae_fiscal         VARCHAR(10),
    -- endereço
    logradouro          VARCHAR(160),
    numero              VARCHAR(12),
    complemento         VARCHAR(80),
    bairro              VARCHAR(80),
    cidade              VARCHAR(80),
    uf                  CHAR(2),
    cep                 CHAR(8),
    telefone            VARCHAR(20),
    email               VARCHAR(120),
    website             VARCHAR(160),
    -- personalização (mockup 8.2)
    logotipo_path       VARCHAR(500),
    fundo_tela_path     VARCHAR(500),
    impressora_matricial VARCHAR(160),
    impressora_cupom    VARCHAR(160),
    -- crédito de NFC-e/NF-e junto ao gateway (credenciais ficam no cofre do serviço)
    certificado_path    VARCHAR(500),
    ativa               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_empresa_upd BEFORE UPDATE ON empresa
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE filial (
    id            BIGSERIAL PRIMARY KEY,
    empresa_id    BIGINT NOT NULL REFERENCES empresa (id),
    nome          VARCHAR(120) NOT NULL,
    cnpj          CHAR(14),
    logradouro    VARCHAR(160),
    numero        VARCHAR(12),
    complemento   VARCHAR(80),
    bairro        VARCHAR(80),
    cidade        VARCHAR(80),
    uf            CHAR(2),
    cep           CHAR(8),
    telefone      VARCHAR(20),
    email         VARCHAR(120),
    ativa         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_filial_empresa ON filial (empresa_id);
CREATE TRIGGER trg_filial_upd BEFORE UPDATE ON filial
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- USUÁRIOS / SESSÃO / RBAC
-- ===========================================================================
CREATE TABLE usuario (
    id              BIGSERIAL PRIMARY KEY,
    filial_id       BIGINT REFERENCES filial (id),
    nome            VARCHAR(120)   NOT NULL,
    login           VARCHAR(60)    NOT NULL UNIQUE,
    senha_hash      VARCHAR(255)   NOT NULL,          -- argon2/bcrypt (a definir)
    nivel_acesso    nivel_acesso   NOT NULL DEFAULT 'operador',
    email           VARCHAR(120),
    ativo           BOOLEAN        NOT NULL DEFAULT TRUE,
    falhas_login    INTEGER        NOT NULL DEFAULT 0, -- bloqueio por tentativas (PRD §5)
    bloqueado_em    TIMESTAMPTZ,
    ultimo_login    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT now()
);
CREATE INDEX idx_usuario_nome ON usuario (nome);
CREATE TRIGGER trg_usuario_upd BEFORE UPDATE ON usuario
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE usuario_sessao (
    id            BIGSERIAL PRIMARY KEY,
    usuario_id    BIGINT NOT NULL REFERENCES usuario (id),
    token_hash    VARCHAR(64)  NOT NULL UNIQUE,        -- SHA-256 do token (sem armazenar o token cru)
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expira_em     TIMESTAMPTZ  NOT NULL,               -- expiração por inatividade (PRD §5)
    encerrada     BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_sessao_usuario ON usuario_sessao (usuario_id, expira_em);

-- ===========================================================================
-- CADASTROS
-- ===========================================================================
CREATE TABLE cliente (
    id              BIGSERIAL PRIMARY KEY,
    filial_id       BIGINT NOT NULL REFERENCES filial (id),
    nome_razao      VARCHAR(200) NOT NULL,
    tipo_pessoa     tipo_pessoa  NOT NULL DEFAULT 'pf',
    cpf_cnpj        VARCHAR(18)  UNIQUE,        -- aceita máscara; normalização no app
    inscricao_estadual VARCHAR(20),
    data_nascimento DATE,                        -- relatório de aniversariantes
    email           VARCHAR(120),
    telefone        VARCHAR(20),
    celular         VARCHAR(20),
    logradouro      VARCHAR(160),
    numero          VARCHAR(12),
    complemento     VARCHAR(80),
    bairro          VARCHAR(80),
    cidade          VARCHAR(80),
    uf              CHAR(2),
    cep             CHAR(8),
    foto_path       VARCHAR(500),
    observacoes     TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cliente_nome   ON cliente (nome_razao);
CREATE INDEX idx_cliente_dt_nas ON cliente (data_nascimento) WHERE data_nascimento IS NOT NULL;
CREATE TRIGGER trg_cliente_upd BEFORE UPDATE ON cliente
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE fornecedor (
    id              BIGSERIAL PRIMARY KEY,
    filial_id       BIGINT NOT NULL REFERENCES filial (id),
    nome_razao      VARCHAR(200) NOT NULL,
    tipo_pessoa     tipo_pessoa  NOT NULL DEFAULT 'pj',
    cpf_cnpj        VARCHAR(18)  UNIQUE,
    inscricao_estadual VARCHAR(20),
    email           VARCHAR(120),
    telefone        VARCHAR(20),
    celular         VARCHAR(20),
    contato_nome    VARCHAR(120),
    logradouro      VARCHAR(160),
    numero          VARCHAR(12),
    complemento     VARCHAR(80),
    bairro          VARCHAR(80),
    cidade          VARCHAR(80),
    uf              CHAR(2),
    cep             CHAR(8),
    observacoes     TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_fornecedor_nome ON fornecedor (nome_razao);
CREATE TRIGGER trg_fornecedor_upd BEFORE UPDATE ON fornecedor
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE funcionario (
    id              BIGSERIAL PRIMARY KEY,
    filial_id       BIGINT NOT NULL REFERENCES filial (id),
    nome            VARCHAR(120) NOT NULL,
    cpf             VARCHAR(18)  UNIQUE,
    cargo           VARCHAR(60),                 -- ex.: Atendente, Operador de Impressão
    email           VARCHAR(120),
    telefone        VARCHAR(20),
    data_nascimento DATE,                         -- aniversariantes de funcionários (opcional)
    data_admissao   DATE,
    e_vendedor      BOOLEAN NOT NULL DEFAULT FALSE,
    e_atendente     BOOLEAN NOT NULL DEFAULT FALSE,
    e_producao      BOOLEAN NOT NULL DEFAULT FALSE,
    comissao_pct    NUMERIC(6,3) DEFAULT 0,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_funcionario_nome ON funcionario (nome);
CREATE TRIGGER trg_funcionario_upd BEFORE UPDATE ON funcionario
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- PRODUTOS / SERVIÇOS / ESTOQUE
-- ===========================================================================
CREATE TABLE produto_categoria (
    id          BIGSERIAL PRIMARY KEY,
    filial_id   BIGINT REFERENCES filial (id),
    nome        VARCHAR(80) NOT NULL UNIQUE,
    description VARCHAR(255),
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_produto_categoria_upd BEFORE UPDATE ON produto_categoria
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE produto (
    id                 BIGSERIAL PRIMARY KEY,
    filial_id          BIGINT NOT NULL REFERENCES filial (id),
    categoria_id       BIGINT REFERENCES produto_categoria (id),
    codigo             VARCHAR(30)  NOT NULL UNIQUE,   -- código interno de busca (F3)
    codigo_barras      VARCHAR(30),
    nome               VARCHAR(160) NOT NULL,
    descricao          TEXT,
    tipo               tipo_produto NOT NULL DEFAULT 'produto',
    unidade            VARCHAR(12)  NOT NULL DEFAULT 'un',  -- un, m, m2, resma, ml...
    controla_estoque   BOOLEAN      NOT NULL DEFAULT TRUE,  -- serviço não baixa estoque
    preco_custo        NUMERIC(14,2) NOT NULL DEFAULT 0,
    preco_venda        NUMERIC(14,2) NOT NULL DEFAULT 0,
    estoque_minimo     NUMERIC(12,3) NOT NULL DEFAULT 0,    -- relatório de reposição
    dimensoes          VARCHAR(40),                          -- ex.: '20x30 cm' (item de OS usa o próprio)
    foto1_path         VARCHAR(500),
    foto2_path         VARCHAR(500),
    bloqueado_reajuste BOOLEAN NOT NULL DEFAULT FALSE,       -- protegido do reajuste em bloco (8.1)
    ativo              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_produto_nome        ON produto (nome);
CREATE INDEX idx_produto_categoria   ON produto (categoria_id);
CREATE INDEX idx_produto_codigo_busca ON produto (codigo);
CREATE TRIGGER trg_produto_upd BEFORE UPDATE ON produto
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Saldo por filial × produto (saldo NÃO é derivado do kardex por performance)
CREATE TABLE produto_estoque (
    id           BIGSERIAL PRIMARY KEY,
    filial_id    BIGINT NOT NULL REFERENCES filial (id),
    produto_id   BIGINT NOT NULL REFERENCES produto (id),
    saldo        NUMERIC(12,3) NOT NULL DEFAULT 0,
    reservado    NUMERIC(12,3) NOT NULL DEFAULT 0,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (filial_id, produto_id)
);
CREATE INDEX idx_estoque_produto ON produto_estoque (produto_id, filial_id);

-- Kardex (histórico imutável; saldo_anterior/posterior p/ trilha)
CREATE TABLE movimento_estoque (
    id                BIGSERIAL PRIMARY KEY,
    filial_id         BIGINT NOT NULL REFERENCES filial (id),
    produto_id        BIGINT NOT NULL REFERENCES produto (id),
    tipo              tipo_mov_estoque NOT NULL,
    origem            origem_mov       NOT NULL,
    documento_id      BIGINT,               -- id genérico: venda_balcao/os/pedido_compra/(ajuste manual NULL)
    quantidade        NUMERIC(12,3) NOT NULL CHECK (quantidade <> 0),
    saldo_anterior    NUMERIC(12,3) NOT NULL,
    saldo_posterior   NUMERIC(12,3) NOT NULL,
    motivo            VARCHAR(255),
    usuario_id        BIGINT REFERENCES usuario (id),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_kardex_produto ON movimento_estoque (produto_id, criado_em DESC);
CREATE INDEX idx_kardex_origem  ON movimento_estoque (origem, documento_id);

-- ===========================================================================
-- MOVIMENTO: ORDEM DE SERVIÇO / ORÇAMENTO
-- (Orçamento e OS compartilham a mesma base; conversão gera filho tipo 'os'
--  apontando para o orçamento de origem — telas_e_fluxos §2.1)
-- ===========================================================================
CREATE TABLE ordem_servico (
    id                   BIGSERIAL PRIMARY KEY,
    filial_id            BIGINT NOT NULL REFERENCES filial (id),
    numero               INTEGER NOT NULL DEFAULT nextval('seq_os_numero'),
    tipo                 tipo_os   NOT NULL DEFAULT 'os',
    status               status_os NOT NULL DEFAULT 'aberto',
    orcamento_origem_id  BIGINT REFERENCES ordem_servico (id),
    cliente_id           BIGINT REFERENCES cliente (id),
    vendedor_id          BIGINT REFERENCES funcionario (id),
    atendente_id         BIGINT REFERENCES funcionario (id),
    data_emissao         DATE      NOT NULL DEFAULT CURRENT_DATE,
    data_previsao_entrega DATE,
    data_conclusao       DATE,
    data_entrega         DATE,
    desconto             NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_itens          NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_total          NUMERIC(14,2) NOT NULL DEFAULT 0,
    forma_pagamento      forma_pagamento,
    observacoes          TEXT,
    criado_por           BIGINT REFERENCES usuario (id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ordem_servico.orcamento_origem_id IS NULL OR ordem_servico.orcamento_origem_id <> ordem_servico.id)
);
CREATE INDEX idx_os_status    ON ordem_servico (status, data_emissao);
CREATE INDEX idx_os_cliente   ON ordem_servico (cliente_id);
CREATE INDEX idx_os_numero    ON ordem_servico (filial_id, numero);
CREATE TRIGGER trg_os_upd BEFORE UPDATE ON ordem_servico
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE ordem_servico_item (
    id                 BIGSERIAL PRIMARY KEY,
    ordem_servico_id   BIGINT NOT NULL REFERENCES ordem_servico (id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL,
    produto_id         BIGINT REFERENCES produto (id),
    descricao_avulsa   VARCHAR(255),          -- item sem produto cadastrado (freqüente em gráfica)
    quantidade         NUMERIC(12,3) NOT NULL DEFAULT 1,
    dimensoes          VARCHAR(40),           -- ex.: '1.20 x 0.90 m'
    valor_unitario     NUMERIC(14,2) NOT NULL DEFAULT 0,
    desconto           NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_total        NUMERIC(14,2) NOT NULL DEFAULT 0,
    executado          BOOLEAN NOT NULL DEFAULT FALSE,  -- progresso na produção (3.2)
    UNIQUE (ordem_servico_id, seq)
);
CREATE INDEX idx_os_item_produto ON ordem_servico_item (produto_id);

-- ===========================================================================
-- MOVIMENTO: VENDA BALCÃO
-- ===========================================================================
CREATE TABLE venda_balcao (
    id                 BIGSERIAL PRIMARY KEY,
    filial_id          BIGINT NOT NULL REFERENCES filial (id),
    numero             INTEGER NOT NULL DEFAULT nextval('seq_venda_numero'),
    status             status_venda NOT NULL DEFAULT 'ok',
    cliente_id         BIGINT REFERENCES cliente (id),   -- NULL = consumidor final
    vendedor_id        BIGINT REFERENCES funcionario (id),
    operador_caixa     BIGINT REFERENCES usuario (id),
    data_venda         DATE NOT NULL DEFAULT CURRENT_DATE,
    valor_itens        NUMERIC(14,2) NOT NULL DEFAULT 0,
    desconto           NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_total        NUMERIC(14,2) NOT NULL DEFAULT 0,
    forma_pagamento    forma_pagamento NOT NULL,
    parcelas           INTEGER NOT NULL DEFAULT 1,        -- parcelamento (fiado/cartão)
    caixa_id           BIGINT,                            -- preenchido no lançamento do caixa
    documento_fiscal_id BIGINT,                           -- lançado após emissão (6.1)
    observacoes        TEXT,
    criado_por         BIGINT REFERENCES usuario (id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (venda_balcao.status <> 'ok' OR venda_balcao.operador_caixa IS NOT NULL)
);
CREATE INDEX idx_venda_status ON venda_balcao (status, data_venda);
CREATE INDEX idx_venda_cliente ON venda_balcao (cliente_id);
CREATE TRIGGER trg_venda_upd BEFORE UPDATE ON venda_balcao
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE venda_balcao_item (
    id                 BIGSERIAL PRIMARY KEY,
    venda_balcao_id    BIGINT NOT NULL REFERENCES venda_balcao (id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL,
    produto_id         BIGINT REFERENCES produto (id),
    descricao_avulsa   VARCHAR(255),
    quantidade         NUMERIC(12,3) NOT NULL DEFAULT 1,
    valor_unitario     NUMERIC(14,2) NOT NULL DEFAULT 0,
    desconto           NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_total        NUMERIC(14,2) NOT NULL DEFAULT 0,
    UNIQUE (venda_balcao_id, seq)
);
CREATE INDEX idx_venda_item_produto ON venda_balcao_item (produto_id);

-- ===========================================================================
-- MOVIMENTO: PEDIDO DE COMPRA
-- ===========================================================================
CREATE TABLE pedido_compra (
    id                 BIGSERIAL PRIMARY KEY,
    filial_id          BIGINT NOT NULL REFERENCES filial (id),
    numero             INTEGER NOT NULL DEFAULT nextval('seq_pedido_numero'),
    status             status_pedido NOT NULL DEFAULT 'aberto',
    fornecedor_id      BIGINT REFERENCES fornecedor (id),
    data_pedido        DATE NOT NULL DEFAULT CURRENT_DATE,
    previsao_entrega   DATE,
    data_recebimento   DATE,
    valor_total        NUMERIC(14,2) NOT NULL DEFAULT 0,
    observacoes        TEXT,
    solicitante_id     BIGINT REFERENCES usuario (id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pedido_status ON pedido_compra (status, data_pedido);
CREATE INDEX idx_pedido_fornecedor ON pedido_compra (fornecedor_id);
CREATE TRIGGER trg_pedido_upd BEFORE UPDATE ON pedido_compra
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE pedido_compra_item (
    id                 BIGSERIAL PRIMARY KEY,
    pedido_compra_id   BIGINT NOT NULL REFERENCES pedido_compra (id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL,
    produto_id         BIGINT NOT NULL REFERENCES produto (id),
    descricao_avulsa   VARCHAR(255),
    quantidade         NUMERIC(12,3) NOT NULL DEFAULT 1,
    quantidade_recebida NUMERIC(12,3) NOT NULL DEFAULT 0,
    valor_unitario     NUMERIC(14,2) NOT NULL DEFAULT 0,
    valor_total        NUMERIC(14,2) NOT NULL DEFAULT 0,
    UNIQUE (pedido_compra_id, seq)
);
CREATE INDEX idx_pedido_item_produto ON pedido_compra_item (produto_id);

-- ===========================================================================
-- AGENDAMENTO (produção / entregas)
-- ===========================================================================
CREATE TABLE agendamento (
    id                 BIGSERIAL PRIMARY KEY,
    filial_id          BIGINT NOT NULL REFERENCES filial (id),
    tipo               tipo_agenda NOT NULL DEFAULT 'producao',
    status             status_agenda NOT NULL DEFAULT 'agendado',
    titulo             VARCHAR(160) NOT NULL,
    descricao          TEXT,
    data_hora_inicio   TIMESTAMPTZ NOT NULL,
    data_hora_fim      TIMESTAMPTZ,
    ordem_servico_id   BIGINT REFERENCES ordem_servico (id),
    usuario_id         BIGINT REFERENCES usuario (id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agenda_inicio ON agendamento (data_hora_inicio);
CREATE TRIGGER trg_agendamento_upd BEFORE UPDATE ON agendamento
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- FINANCEIRO
-- ===========================================================================
CREATE TABLE plano_contas (
    id           BIGSERIAL PRIMARY KEY,
    filial_id    BIGINT REFERENCES filial (id),
    codigo       VARCHAR(20) NOT NULL,
    nome         VARCHAR(120) NOT NULL,
    tipo         tipo_plano_conta NOT NULL,
    pai_id       BIGINT REFERENCES plano_contas (id),
    ativo        BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (filial_id, codigo)
);
CREATE INDEX idx_plano_pai ON plano_contas (pai_id);

CREATE TABLE conta_receber (
    id                BIGSERIAL PRIMARY KEY,
    filial_id         BIGINT NOT NULL REFERENCES filial (id),
    cliente_id        BIGINT REFERENCES cliente (id),
    plano_conta_id    BIGINT REFERENCES plano_contas (id),
    venda_balcao_id   BIGINT REFERENCES venda_balcao (id),
    ordem_servico_id  BIGINT REFERENCES ordem_servico (id),
    descricao         VARCHAR(255) NOT NULL,
    parcela           INTEGER NOT NULL DEFAULT 1,
    total_parcelas    INTEGER NOT NULL DEFAULT 1,
    vencimento        DATE NOT NULL,
    valor             NUMERIC(14,2) NOT NULL,
    valor_pago        NUMERIC(14,2) NOT NULL DEFAULT 0,
    status            status_conta NOT NULL DEFAULT 'aberta',
    data_pagamento    DATE,
    usuario_baixa_id  BIGINT REFERENCES usuario (id),
    observacoes       TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cr_vencimento ON conta_receber (status, vencimento);
CREATE INDEX idx_cr_cliente    ON conta_receber (cliente_id);
CREATE TRIGGER trg_cr_upd BEFORE UPDATE ON conta_receber
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE conta_pagar (
    id                BIGSERIAL PRIMARY KEY,
    filial_id         BIGINT NOT NULL REFERENCES filial (id),
    fornecedor_id     BIGINT REFERENCES fornecedor (id),
    plano_conta_id    BIGINT REFERENCES plano_contas (id),
    pedido_compra_id  BIGINT REFERENCES pedido_compra (id),
    descricao         VARCHAR(255) NOT NULL,
    parcela           INTEGER NOT NULL DEFAULT 1,
    total_parcelas    INTEGER NOT NULL DEFAULT 1,
    vencimento        DATE NOT NULL,
    valor             NUMERIC(14,2) NOT NULL,
    valor_pago        NUMERIC(14,2) NOT NULL DEFAULT 0,
    status            status_conta NOT NULL DEFAULT 'aberta',
    data_pagamento    DATE,
    usuario_baixa_id  BIGINT REFERENCES usuario (id),
    observacoes       TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cp_vencimento ON conta_pagar (status, vencimento);
CREATE INDEX idx_cp_fornecedor ON conta_pagar (fornecedor_id);
CREATE TRIGGER trg_cp_upd BEFORE UPDATE ON conta_pagar
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- CAIXA
-- ===========================================================================
CREATE TABLE caixa (
    id                    BIGSERIAL PRIMARY KEY,
    filial_id             BIGINT NOT NULL REFERENCES filial (id),
    usuario_id            BIGINT NOT NULL REFERENCES usuario (id),
    status                status_caixa NOT NULL DEFAULT 'aberto',
    data_abertura         TIMESTAMPTZ NOT NULL DEFAULT now(),
    valor_abertura        NUMERIC(14,2) NOT NULL DEFAULT 0,
    data_fechamento       TIMESTAMPTZ,
    valor_esperado        NUMERIC(14,2),    -- soma dos lançamentos (fechamento)
    valor_informado       NUMERIC(14,2),    -- conferência física
    diferenca             NUMERIC(14,2),    -- divergência registrada (PRD §8)
    observacoes           TEXT,
    closed_user_id        BIGINT REFERENCES usuario (id),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_caixa_status ON caixa (status, data_abertura);
CREATE TRIGGER trg_caixa_upd BEFORE UPDATE ON caixa
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE movimento_caixa (
    id                BIGSERIAL PRIMARY KEY,
    caixa_id          BIGINT NOT NULL REFERENCES caixa (id),
    tipo              tipo_mov_caixa NOT NULL,
    venda_balcao_id   BIGINT REFERENCES venda_balcao (id),
    conta_receber_id  BIGINT REFERENCES conta_receber (id),
    conta_pagar_id    BIGINT REFERENCES conta_pagar (id),
    descricao         VARCHAR(255),
    valor             NUMERIC(14,2) NOT NULL,
    usuario_id        BIGINT REFERENCES usuario (id),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_movcaixa_caixa ON movimento_caixa (caixa_id, criado_em);

-- ===========================================================================
-- FISCAL (NF-e / NFC-e via gateway; vínculo + retorno + contingência)
-- ===========================================================================
CREATE TABLE documento_fiscal (
    id                BIGSERIAL PRIMARY KEY,
    filial_id         BIGINT NOT NULL REFERENCES filial (id),
    modelo            modelo_fiscal NOT NULL,
    numero            INTEGER,
    serie             INTEGER,
    chave_acesso      VARCHAR(44),
    status            status_fiscal NOT NULL DEFAULT 'rascunho',
    venda_balcao_id   BIGINT REFERENCES venda_balcao (id),
    ordem_servico_id  BIGINT REFERENCES ordem_servico (id),
    cliente_id        BIGINT REFERENCES cliente (id),
    valor_nota        NUMERIC(14,2) NOT NULL DEFAULT 0,
    xml_path          VARCHAR(500),      -- retido p/ 5 anos (PRD §6)
    danfe_path        VARCHAR(500),
    protocolo         VARCHAR(30),
    mensagem_retorno  TEXT,              -- motivo de rejeição (6.2)
    retorno_json      JSONB,             -- payload cru do gateway (auditoria)
    contingencia      BOOLEAN NOT NULL DEFAULT FALSE,
    tentativas        INTEGER NOT NULL DEFAULT 0,
    criado_por        BIGINT REFERENCES usuario (id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_df_status ON documento_fiscal (status, created_at);
CREATE INDEX idx_df_venda  ON documento_fiscal (venda_balcao_id) WHERE venda_balcao_id IS NOT NULL;
CREATE INDEX idx_df_os     ON documento_fiscal (ordem_servico_id) WHERE ordem_servico_id IS NOT NULL;
CREATE INDEX idx_df_chave  ON documento_fiscal (chave_acesso);
CREATE TRIGGER trg_df_upd BEFORE UPDATE ON documento_fiscal
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===========================================================================
-- REAJUSTE DE PREÇOS EM BLOCO (8.1) — trilha de auditoria simples (PRD §1.3)
-- ===========================================================================
CREATE TABLE preco_reajuste_historico (
    id             BIGSERIAL PRIMARY KEY,
    filial_id      BIGINT NOT NULL REFERENCES filial (id),
    usuario_id     BIGINT NOT NULL REFERENCES usuario (id),
    tipo_reajuste  VARCHAR(12) NOT NULL CHECK (tipo_reajuste IN ('percentual', 'valor_fixo')),
    valor_reajuste NUMERIC(14,4) NOT NULL,      -- pct (ex.: 10.5 = +10,5%) ou valor fixo
    criterio       TEXT NOT NULL,               -- 'todos' | 'categoria:<id>' | 'produto:<id>,...'
    itens_afetados INTEGER NOT NULL,
    detalhes       JSONB NOT NULL,              -- [{produto_id, nome, preco_antes, preco_depois}]
    executado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reajuste_data ON preco_reajuste_historico (executado_em DESC);

COMMIT;