# Documento de Requisitos do Produto (PRD)
## PrintGest ERP — Sistema de Gestão para Gráfica Rápida

**Versão:** 2.2.0
**Data:** 20 de outubro de 2026
**Status:** Rascunho para validação
**Baseline:** Evolui o PRD v2.1.0. Congela o **real implementado** (backend + desktop), introduz o **modelo comercial de planos** com módulos por plano e formaliza o **licenciamento multi-contrato** (Contrato C padrão + Contrato B v4.0 atrás de flag).

---

## Histórico de Revisões

| Versão | Alterações |
|---|---|
| 1.0.0 | Versão inicial enxuta, sem licenciamento via terceiro. |
| 1.2.0 (RedGest) | Versão superdimensionada: Local API Service, licenciamento offline-first com hardware ID/rebind/tamper, blind index de PII, Documenso, SOX/ISO 9001/WCAG. |
| 2.0.0 | Recalibrada para o caso real: 5 máquinas na mesma rede com internet, licenciamento online-first via RedGest, LGPD proporcional ao porte, backlog explícito. |
| 2.1.0 | Licenciamento migrado para **chave de produto validada online** (RedGest Contrato C). Resiliência (tolerância de 72 h, backoff, estados) mantida. |
| **2.2.0** | Congela o implementado (módulos + telas), introduz os **planos Essencial / Profissional / Enterprise** com **módulos habilitados por plano** aplicados **no servidor via `entitlements`**, e formaliza o **multi-contrato** de licenciamento (C padrão, B v4.0 atrás de `PRINTGEST_REDGEST_CONTRATO`). Projetos (Kanban) entra no escopo pago; módulos pendentes ganham fase e plano-alvo. |

---

## 1. Visão Geral

### 1.1 Propósito

Sistema ERP desktop (Windows) para gráficas rápidas de pequeno porte, operando em rede local com **até 5 estações**, com uma máquina atuando como servidor local (Local API Service + PostgreSQL embarcado). Gerencia Ordens de Serviço, orçamentos, vendas de balcão, estoque, financeiro, fiscal, projetos (Kanban) e relatórios.

### 1.2 Contexto de operação

- Todas as estações estão na mesma rede local, **com internet disponível como regra**.
- Offline é tratado como **falha temporária de conectividade**, não como modo de uso planejado.
- Uma máquina da rede roda o **Local API Service**; as demais estações acessam esse serviço via rede interna — nenhuma estação-cliente acessa o PostgreSQL ou a internet diretamente para fins do ERP.
- Expansão para filiais é suportada pelo modelo de dados (`filial_id` em todas as tabelas operacionais), mas **não é requisito da primeira entrega**.

### 1.3 Público-alvo

Donos e operadores de gráficas rápidas de pequeno porte no Brasil, tipicamente com 1 a 5 estações de trabalho em uma única unidade, com expansão possível para filiais no médio prazo.

### 1.4 Escopo desta versão

Esta revisão **congela o estado real** do produto e passa a tratar o licenciamento como **comercial** (planos + módulos). O que entra:

1. **Modelo comercial de planos** (§3): Essencial, Profissional e Enterprise, com conjuntos de módulos habilitados.
2. **Catálogo de módulos e telas** (§5 e §6): inventário do que existe hoje, com a tela correspondente, e do que é planejado.
3. **Enforcement de plano no servidor** (§4): módulos habilitados derivados do `entitlements` da licença; o desktop apenas oculta menu (usabilidade), nunca é a autoridade.
4. **Licenciamento multi-contrato** (§4.4): Contrato C continua padrão; Contrato B v4.0 entra atrás de flag, sem alterar o comportamento do C.

### 1.5 Escopo excluído (backlog — ver §10)

- Multi-filial ativo (telas, consolidação entre filiais).
- Criptografia de PII com blind index (AES-GCM + HMAC + HKDF).
- Assinatura digital via Documenso.
- Curva ABC de estoque, conciliação bancária OFX/CSV.
- Réplica/sincronização multi-servidor.
- Aplicativo móvel.
- Compliance corporativo não aplicável (SOX, ISO 9001, WCAG) — mantêm-se apenas LGPD e obrigações fiscais reais.

### 1.6 Decisões-chave desta versão

| # | Decisão | Resumo |
|---|---|---|
| D1 | Local API Service continua obrigatório | Centraliza acesso ao banco e RBAC; estações-cliente nunca acessam PostgreSQL diretamente. |
| D2 | Licenciamento online-first, agora **multi-contrato** | Contrato C (chave de produto) é o padrão; Contrato B v4.0 (`cnpj` + `codigo_licenca`, credenciais M2M) entra atrás de flag. A instalação é identificada por fingerprint estável de hardware. |
| D3 | LGPD proporcional | RBAC por usuário/nível + backup substituem criptografia de campo como medida inicial. Criptografia de PII permanece backlog. |
| D4 | **Planos comerciais com módulos habilitados** | Três planos (Essencial/Profissional/Enterprise). O conjunto de módulos vem do `entitlements` da licença, **aplicado no servidor**. |
| D5 | **Desktop não é autoridade de plano** | O menu oculta módulos não contratados por usabilidade; a rota correspondente responde `403` se chamada. |
| D6 | Multi-filial: dado pronto, funcionalidade não ativada | Tabelas já usam `filial_id`; telas e consolidação ficam para quando houver uma segunda unidade. |
| D7 | Projetos (Kanban) é módulo pago | Quadro Kanban + cartão rico (etiquetas, checklists, comentários, atividade) entram a partir do **Profissional**. |

---

## 2. Arquitetura

### 2.1 Topologia (até 5 máquinas)

```
[Estacao 1] ---\
[Estacao 2] ----\
[Estacao 3] -----> Local API Service (FastAPI) ---> PostgreSQL
[Estacao 4] ----/         (roda em 1 das 5 maquinas)
[Estacao 5] ---/                   |
                                    v
                          RedGest (licenca: validacao,
                          plano e modulos habilitados,
                          so esta maquina acessa a internet
                          para fins de licenciamento)
```

- A máquina que roda o Local API Service deve permanecer ligada durante o expediente.
- Requisito mínimo recomendado: 8 GB RAM, SSD, Windows 10/11 64 bits.
- Ponto único de falha aceito conscientemente neste porte; mitigado registrando o Local API Service e o PostgreSQL como serviços Windows com início automático.

### 2.2 Stack técnica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Interface desktop | PySide6 (Qt6) |
| Backend local | FastAPI (Local API Service) |
| Banco de dados | PostgreSQL 15+ |
| ORM / Migrações | SQLAlchemy 2.x + Alembic (aplicadas no startup, idempotentes) |
| Impressão | QPrinter (nativo Qt) |
| Emissão fiscal | Gateway REST (Focus NFe / PlugNotas / eNotas) — **planejado** |
| Empacotamento | PyInstaller + Inno Setup (instalador único com PostgreSQL embarcado) |

### 2.3 Camadas do backend

```
app/api/        -> routers + schemas Pydantic (contrato HTTP)  -- prefixo /v1
app/services/   -> regras de negocio (transacionais quando multi-tabela)
app/models/     -> SQLAlchemy 2.x
app/deps.py     -> auth, sessao, RBAC, current_user
```

- Toda escrita que altera mais de uma tabela é uma transação em serviço (ex.: venda → baixa de estoque + kardex).
- RBAC e gating de plano são aplicados **no backend**.
- Valores monetários/quantidade sempre `Decimal`/`NUMERIC`, nunca `float`.
- Envelope de resposta: `{"data": ...}` (item) e `{"data": [...], "meta": {...}}` (lista).

### 2.4 Camadas do desktop

```
desktop/printgest/core/   -> client HTTP (httpx) + sessao/token
desktop/printgest/ui/     -> janelas, shell e modulos (PySide6)
desktop/printgest/ui/modulos/ -> uma pagina por modulo
desktop/printgest/printing/   -> QPrinter
```

---

## 3. Modelo Comercial: Planos e Módulos

### 3.1 Princípio

O PrintGest é vendido em **três planos**. Cada plano habilita um **conjunto de módulos** e um **limite de estações**. O plano e os módulos habilitados são **emitidos pelo RedGest** junto com a licença e chegam ao Local API Service no campo `entitlements`:

```json
{
  "plano": "profissional",
  "max_estacoes": 5,
  "modulos_habilitados": ["cadastros", "movimento", "estoque", "projetos", "financeiro", "relatorios"]
}
```

O desktop **exibe** o plano no detalhe da licença (botão "Licença" no cabeçalho) e **oculta** do menu os módulos não habilitados. A autoridade, porém, é o servidor (§4).

### 3.2 Comparativo de planos

| Plano | Perfil | Estações | Módulos habilitados |
|---|---|---|---|
| **Essencial** | Gráfica começando; foco em balcão e produção | até **2** | Cadastros, Movimento (OS/Orçamento/PDV), Estoque |
| **Profissional** | Operação completa com gestão | até **5** | Essencial + Projetos (Kanban), Financeiro, Relatórios |
| **Enterprise** | Operação completa + fiscal e integrações | até **10** | Profissional + Fiscal (emissão NF-e/NFC-e), Multi-filial, API de integração |

> Observação: o **limite de `max_estacoes`** é um teto contratual; a topologia suportada hoje é de 5 estações (§2.1). Planos com mais de 5 estações exigem revisão da arquitetura de rede (backlog).

### 3.3 Matriz de módulos por plano

Módulos canônicos usados no `entitlements.modulos_habilitados`:

| Módulo (id canônico) | Essencial | Profissional | Enterprise |
|---|:---:|:---:|:---:|
| `cadastros` (clientes, fornecedores, produtos, serviços, categorias, funcionários) | ✅ | ✅ | ✅ |
| `movimento` (OS, Orçamento, Venda Balcão/PDV) | ✅ | ✅ | ✅ |
| `estoque` (consulta, movimentação, reposição) | ✅ | ✅ | ✅ |
| `agendamento` (calendário de produção/entregas) | ✅ | ✅ | ✅ |
| `projetos` (quadro Kanban + cartão rico) | — | ✅ | ✅ |
| `financeiro` (caixa, contas a pagar/receber, plano de contas) | — | ✅ | ✅ |
| `relatorios` (vendas, clientes, serviços, aniversariantes) | — | ✅ | ✅ |
| `fiscal` (documentos + emissão NF-e/NFC-e) | — | — | ✅ |
| `configuracoes` (empresa, personalização, reajuste, usuários) | ✅ | ✅ | ✅ |
| `multifilial` | — | — | ✅ (planejado) |
| `api_integracao` | — | — | ✅ (planejado) |

Regras da matriz:

- **`cadastros`, `movimento`, `estoque`, `agendamento` e `configuracoes`** formam o **núcleo operacional** presente em todos os planos (é o que uma gráfica precisa para operar no balcão).
- **`projetos`, `financeiro` e `relatorios`** são o salto de "operar" para "gerir" — entram no **Profissional**.
- **`fiscal`** (emissão real de NF-e/NFC-e) é o diferencial de **Enterprise**, por envolver custo variável de gateway e responsabilidade fiscal.
- Módulos planejados (`multifilial`, `api_integracao`) já nascem com o id canônico reservado para não quebrar o contrato de `entitlements`.

### 3.4 Associação módulo → telas

A tabela abaixo liga cada módulo às telas do desktop (§5) e às rotas do backend (§6). É a referência para o gating.

| Módulo | Telas (desktop) | Rotas (backend) |
|---|---|---|
| `cadastros` | Clientes, Fornecedores, Produtos & Serviços, Categorias, Funcionários | `/v1/clientes`, `/v1/fornecedores`, `/v1/produtos`, `/v1/categorias`, `/v1/funcionarios` |
| `movimento` | PDV (Venda Balcão), Gestão de O.S., Orçamentos | `/v1/vendas`, `/v1/os` |
| `estoque` | Consulta de Estoque, Movimentação Manual, Reposição, Kardex | `/v1/estoque` |
| `agendamento` | Agendamento (Calendário/Lista) | `/v1/agendamento` |
| `projetos` | Projetos (Quadro Kanban + Lista) | `/v1/projetos/*` |
| `financeiro` | Financeiro (Caixa, Contas a Receber, Contas a Pagar, Plano de Contas) | `/v1/financeiro/*`, `/v1/financeiro/plano-contas` |
| `fiscal` | Fiscal (Documentos Fiscais, Contingência) | `/v1/fiscal/*` |
| `relatorios` | Relatórios (Vendas, Clientes, Serviços, Aniversariantes) | *(agregações no desktop sobre endpoints existentes)* |
| `configuracoes` | Configurações (Empresa, Personalização, Reajuste em Bloco, Usuários) | `/v1/config/*`, `/v1/usuarios` |
| `dashboard` (transversal) | Início (Dashboard) | `/v1/dashboard/resumo` |

> `dashboard` não é vendável por plano: é a tela inicial e existe em todos, com campos filtrados por nível de acesso.

---

## 4. Licenciamento e Enforcement de Plano

### 4.1 Princípio

A licença é emitida e controlada pelo RedGest. Ela carrega **vigência**, **plano** e **módulos habilitados**. Apenas o Local API Service comunica-se com o RedGest; as estações-cliente nunca o fazem diretamente.

### 4.2 Estados derivados (nunca persistidos como verdade)

- `ativa` — `status=ativa` e `expira_em` no futuro (ou vitalícia).
- `tolerancia` — `expira_em` vencido, dentro da tolerância; ainda **escreve**, com aviso.
- `leitura` — tolerância esgotada, ou status local `bloqueada`/`expirada`.
- `revogada` — `status=revogada` (leitura imediata, sem tolerância).
- `nao_ativada` — não há linha local.

`modo_leitura = estado in {leitura, revogada, nao_ativada}`.

### 4.3 Resiliência (indisponibilidade não bloqueia)

- `httpx.HTTPError` (timeout/DNS) e **5xx/429** do RedGest → **503** e **nunca** revogam.
- Sem `redgest_api_key` configurada, a ativação responde **502** antes de qualquer chamada de rede.
- Revogação/bloqueio/expiração só vêm de resposta explícita do RedGest.
- Enquanto o RedGest estiver fora, o sistema opera dentro da vigência + **72 h** de tolerância.
- Revalidação a cada `licenca_revalidar_a_cada_segundos` (default 6 h), com backoff progressivo (60/300/900/3600 s) **com jitter** de ±20%.

### 4.4 Contratos com o RedGest

**Contrato C (padrão).** Chave de produto `XXXX-XXXX-XXXX-XXXX` digitada na 1ª execução; validação online em `POST /api/v1/licencas-software/validar/`, autenticada por HMAC-SHA256 do `Sistema.api_key`. Sem JWT. Depreciado pelo RedGest (sunset **01/03/2027**) — permanece como adapter até a data.

**Contrato B v4.0 (atrás de flag `PRINTGEST_REDGEST_CONTRATO=b`).** Ativação por **CNPJ + código da licença** (`/api/v1/licencas/*`), troca por `client_id`/`client_secret` (guardados no cofre do SO), resposta com `grace_deadline` e `entitlements`. Suporta `hardware_bound` (perfil de hardware + rebind) e `online_periodic` (handshake). Plano detalhado em `docs/migracao_redgest_v4.md`.

O contrato C permanece o default e **não muda de comportamento**; o B ativa por flag, com *dual-run* (cada instalação usa um).

### 4.6 Fluxo de instalação (serial antes do login)

Como em programas licenciados por serial, a **tela de ativação é o gate de instalação** e aparece **antes do login**:

1. No primeiro start, o desktop consulta `GET /v1/licenca` **sem sessão** (rota liberada pelo Local API Service).
2. `nao_ativada` → abre a tela de serial (Contrato C: chave de produto; Contrato B: CNPJ + código) e só segue para o login após validar.
3. `ativa`/`tolerancia` → vai direto ao login.
4. Depois de ativada, a licença fica gravada no banco local e as execuções seguintes **não pedem o serial** de novo; ele só reaparece se a instalação for refeita (sem linha em `licenca`).
5. Estado de leitura/revogação continua tratado **após o login** (a consulta de licença não é bloqueante para o operador entrar em modo leitura).

`PRINTGEST_LICENCA_DESABILITADA=true` mantém o atalho de desenvolvimento (pula a etapa). Para testar o fluxo de instalação, `scripts/limpar_licenca.py --sim` remove a licença local (equivale a reinstalar).

### 4.5 Enforcement de plano no servidor (D4/D5)

O gating de módulos por plano é aplicado **no Local API Service**, em três pontos:

1. **Dependência de módulo nas rotas.** Uma dependência (no mesmo estilo de `require_nivel`/`require_perfis` em `backend/app/deps.py`) verifica se o módulo da rota está em `entitlements.modulos_habilitados`. Não habilitado → **HTTP 403** com mensagem PT-BR clara ("Módulo não incluído no plano contratado.").
2. **Modo leitura (licença).** Já existe middleware que responde **423** em escritas quando `modo_leitura` está ativo, com whitelist para login/licença/health. O gating de plano é ortogonal: 423 fala de licença; 403 fala de plano.
3. **Menu do desktop.** O menu (`desktop/printgest/core/rbac.py`) passa a considerar **RBAC × plano**: o item só aparece se o nível de acesso permitir **e** o módulo estiver habilitado. Continua sendo usabilidade — a rota é a autoridade.

Regras:

- **Sem licença ativa, planos ficam vazios** e nenhum módulo é liberado (o sistema cai no fluxo de ativação).
- **Planos são sempre aditivos**: um plano superior habilita tudo do inferior (ver matriz §3.3).
- **Módulo não habilitado não aparece no menu e a rota responde 403.** Nada de "tela em construção" para módulo não contratado — é ausência explícita.
- **`configuracoes` é do núcleo** (essencial), mas continua restrita a usuários Admin pelo RBAC.

### 4.6 Contrato de `entitlements`

O objeto `entitlements` (campo JSONB já existente em `licenca`) tem o esquema:

| Campo | Tipo | Papel |
|---|---|---|
| `plano` | string | `essencial` \| `profissional` \| `enterprise`. |
| `max_estacoes` | int | Teto contratual de estações. |
| `modulos_habilitados` | string[] | Ids canônicos da matriz §3.3. |
| `cnpj_vinculado` | string \| null | CNPJ da empresa vinculada (quando o RedGest enviar). |
| `max_rebinds` | int \| null | Só `hardware_bound` (Contrato B). |

---

## 5. Módulos e Telas

Legenda: **✅ Implementado** (rota + service + tela + testes) · **⚠️ Parcial** · **🔜 Planejado** (fase indicada).

### 5.1 Acesso e Licenciamento (transversal, todos os planos)

| Tela | Descrição | Estado |
|---|---|---|
| Login (`LoginWindow`) | Usuário/senha; checa saúde do daemon; emite `autenticado`. | ✅ |
| Ativação de Licença (`AtivacaoWindow`) | Formulário **dinâmico por contrato**: Contrato C = chave de produto; Contrato B = CNPJ + código. Stepper de 3 passos; F10 ativa, Esc sai. | ✅ |
| Modo Leitura (`ModoLeituraWindow`) | Explica o que pode (consulta) e o que está suspenso (escrita); diagnóstico de conectividade; F5 renova. | ✅ |
| Banner de tolerância | **Não-bloqueante** (sem botão/modal), com contagem regressiva de 1 min e barra fracionada. Aparece no estado `tolerancia`. | ✅ |
| Banner de modo leitura | Faixa âmbar "Sistema em modo leitura — apenas consultas" no shell. | ✅ |
| Detalhe da licença | Popup pelo botão "Licença": estado, motivo, **plano**, chave, limite/ativações, expiração, tolerância, última tentativa/erro. | ✅ |

### 5.2 Início / Dashboard (transversal)

| Tela | Descrição | Estado |
|---|---|---|
| Início (`PaginaInicial`) | Cartões/KPIs de faturamento, estoque crítico, entregas; atalhos rápidos; campos filtrados por nível (operacional × gerencial). | ✅ |

### 5.3 Cadastros — módulo `cadastros`

| Tela | Descrição | Estado |
|---|---|---|
| Cadastro de Clientes | Lista + formulário; foto; condições de pagamento (adiantado/sinal mutuamente exclusivos). | ✅ |
| Cadastro de Fornecedores | Lista + formulário. | ✅ |
| Cadastro de Produtos & Serviços | Lista + formulário; preço custo/venda; estoque mínimo; fotos. | ✅ |
| Cadastro de Serviços | Variante de produtos (tipo serviço). | ✅ |
| Cadastro de Categorias | Lista simples. | ✅ |
| Cadastro de Funcionários | Lista + formulário; observações. | ✅ |

### 5.4 Movimento — módulo `movimento`

| Tela | Descrição | Estado |
|---|---|---|
| PDV — Venda Balcão | Duas visões (Nova venda / Histórico); busca rápida de produto; totalizador; forma de pagamento; baixa de estoque na mesma transação. | ✅ |
| Gestão de Ordens de Serviço | Lista com filtro por status + formulário (cliente, itens, valores, status); transições de status; cancelamento. | ✅ |
| Orçamentos | Mesma base da OS; conversão em OS; simulação de preço. | ✅ |
| Pedido de Compra | Lista + formulário; confirmação de recebimento gera entrada de estoque e conta a pagar. | 🔜 Fase pós-MVP (modelo já existe) — Profissional |

### 5.5 Estoque — módulo `estoque`

| Tela | Descrição | Estado |
|---|---|---|
| Consulta de Estoque & Bobinas | Saldo atual e mínimo; filtros por categoria e "abaixo do mínimo"; KPIs. | ✅ |
| Movimentação Manual & Kardex | Ajuste/entrada/saída avulsa → kardex; consulta de ficha kardex por produto. | ✅ |
| Relatório de Reposição & Giro | Sugestões de compra com giro e autonomia; badges de criticidade. | ✅ |
| Mais Vendidos | Ranking de itens mais vendidos. | 🔜 Pós-MVP — Profissional |

### 5.6 Agendamento — módulo `agendamento`

| Tela | Descrição | Estado |
|---|---|---|
| Agendamento (Calendário/Lista) | Calendário mensal (grade), painel do dia, criação/edição/conclusão; tipos produção/entrega. | ✅ |

### 5.7 Projetos (Kanban) — módulo `projetos`

| Tela | Descrição | Estado |
|---|---|---|
| Projetos — Quadro (Kanban) | Quadro por filial com listas configuráveis; cartões com responsável, prazo, badge de atraso; drag & drop com ordenação fracionária e controle otimista de versão (409). | ✅ |
| Projetos — Lista | 1 projeto = 1 cartão; filtros; criação/edição/arquivamento. | ✅ |
| Cartão rico | Etiquetas, checklists (progresso), comentários (1 nível, soft-delete), log de atividade append-only; membros; visibilidade PV1–PV5. | ✅ |
| Anexos do cartão | Arquivos e capa. | 🔜 Fase 3 — Profissional |
| Vínculo cartão ↔ O.S. | Sincronização de status com a O.S. (RN2); colunas já existem. | 🔜 Fase 5 — Enterprise |

### 5.8 Financeiro — módulo `financeiro`

| Tela | Descrição | Estado |
|---|---|---|
| Caixa | Abertura, extrato do dia, sangria/suprimento, fechamento com conferência (esperado × informado → diferença). | ✅ |
| Contas a Receber | Lista + baixa (total/parcial). | ✅ |
| Contas a Pagar | Lista + baixa (total/parcial). | ✅ |
| Plano de Contas | CRUD. | ✅ |

### 5.9 Fiscal — módulo `fiscal`

| Tela | Descrição | Estado |
|---|---|---|
| Documentos Fiscais | Lista e detalhe (status, XML, DANFE) — **somente leitura**. | ⚠️ Sem emissão |
| Contingência Fiscal | Aviso e resumo quando o gateway está indisponível. | ✅ |
| Emissão NF-e/NFC-e | Emissão a partir de Venda Balcão ou OS via gateway (Focus NFe como padrão); adapter multi-gateway; armazenamento de XML/DANFE ≥ 5 anos. | 🔜 Enterprise |

### 5.10 Relatórios — módulo `relatorios`

| Tela | Descrição | Estado |
|---|---|---|
| Vendas por Período | Faturamento por intervalo. | ⚠️ Shell com conteúdo leve |
| Clientes que Mais Compram | Ranking de clientes. | ⚠️ Shell com conteúdo leve |
| Serviços Mais Executados | Ranking de serviços. | ⚠️ Shell com conteúdo leve |
| Aniversariantes do Mês | Lista de aniversariantes. | ⚠️ Shell com conteúdo leve |

### 5.11 Configurações — módulo `configuracoes`

| Tela | Descrição | Estado |
|---|---|---|
| Dados da Empresa | Razão social, CNPJ, logotipo. | ✅ |
| Personalização | Fundo de tela, impressoras padrão. | ✅ |
| Reajuste de Preços em Bloco | Simulação + confirmação com senha + trilha de auditoria. | ✅ |
| Usuários e Níveis de Acesso | CRUD de usuários; anti-lockout; reset de senha revoga sessões. | ✅ |

---

## 6. Inventário Técnico (rotas por módulo)

Prefixo raiz `/v1`; `GET /health` fora do prefixo. Envelope `{"data": ...}` / `{"data": [...], "meta": {...}}`.

| Módulo | Rotas principais |
|---|---|
| `auth` | `POST /v1/auth/login`, `POST /v1/auth/logout`, `GET /v1/auth/me`, `POST /v1/auth/trocar-senha` |
| `cadastros` | `/v1/clientes`, `/v1/fornecedores`, `/v1/funcionarios`, `/v1/categorias`, `/v1/produtos` (CRUD: `GET` lista, `GET /{id}`, `POST`, `PUT /{id}`, `DELETE /{id}`) |
| `movimento` | `/v1/os` (lista, detalhe, criar, atualizar, cancelar, `POST /{id}/converter`, `PATCH /{id}/status`) |
| `movimento` | `/v1/vendas` (lista, criar, detalhe, cancelar) |
| `estoque` | `/v1/estoque`, `/v1/estoque/resumo`, `/v1/estoque/reposicao`, `POST /v1/estoque/movimentar`, `GET /v1/estoque/{produto_id}/kardex` |
| `agendamento` | `/v1/agendamento` (lista, criar, detalhe, atualizar, `PATCH /{id}/concluir`, excluir) |
| `projetos` | `/v1/projetos/quadro`, `/v1/projetos/quadro/listas*`, `/v1/projetos/cartoes*`, `/v1/projetos/etiquetas`, `/v1/projetos/cartoes/{id}/checklists*`, `/v1/projetos/cartoes/{id}/comentarios*`, `/v1/projetos/cartoes/{id}/atividade` |
| `financeiro` | `/v1/financeiro/caixa/atual`, `/v1/financeiro/caixa/abrir`, `/v1/financeiro/caixa/{id}/extrato`, `POST .../movimento`, `POST .../fechar`, `/v1/financeiro/contas-receber`, `POST .../{id}/baixa`, `/v1/financeiro/contas-pagar`, `POST .../{id}/baixa`, `/v1/financeiro/plano-contas` |
| `fiscal` | `GET /v1/fiscal/documentos`, `GET /v1/fiscal/documentos/{id}`, `GET /v1/fiscal/resumo` (somente leitura) |
| `relatorios` | *(sem router dedicado; agregações no desktop)* |
| `configuracoes` | `GET/PUT /v1/config/empresa`, `GET /v1/config/reajuste/historico`, `POST /v1/config/reajuste/simular`, `POST /v1/config/reajuste/aplicar`, `/v1/usuarios` |
| `dashboard` | `GET /v1/dashboard/resumo` |
| licença | `GET /v1/licenca`, `POST /v1/licenca/ativar`, `POST /v1/licenca/renovar` |

### 6.1 Modelo de dados (resumo)

- **Core:** `empresa` → `filial` (1:N), `usuario`, `usuario_sessao`, `licenca`.
- **Cadastros:** `cliente`, `fornecedor`, `funcionario`, `produto_categoria`, `produto`, `produto_estoque`, `movimento_estoque`.
- **Movimento:** `ordem_servico` + `ordem_servico_item`, `venda_balcao` + `venda_balcao_item`, `pedido_compra` + `pedido_compra_item`, `agendamento`.
- **Financeiro:** `plano_contas`, `conta_receber`, `conta_pagar`, `caixa`, `movimento_caixa`.
- **Fiscal:** `documento_fiscal`.
- **Config:** `preco_reajuste_historico`.
- **Projetos:** `quadro`, `quadro_lista`, `cartao`, `cartao_membro`, `etiqueta`, `cartao_etiqueta`, `cartao_checklist`, `cartao_checklist_item`, `cartao_comentario`, `cartao_atividade`.

Enums: `NivelAcesso` (admin/gerente/operador/caixa), `TipoOs`, `StatusOs`, `StatusVenda`, `FormaPagamento`, `ModeloFiscal`, `StatusFiscal`, `TipoLista`, `OrigemMembro`, `TipoPlanoConta`, `StatusConta`, `StatusCaixa`, `TipoMovCaixa`, entre outros.

### 6.2 Migrações (cadeia Alembic, head atual)

`d7a1c4e8b2f3` (licença: credenciais Contrato B no cofre) é o **head**. A cadeia vai do baseline `ae9f00b5a9a1` até o head, incluindo licenciamento, projetos Fase 1/2 e chave no cofre. Aplicadas automaticamente no startup (idempotente).

---

## 7. RBAC (simplificado)

RBAC **não hierárquico** por perfil (matriz explícita), com níveis:

| Nível | Escopo |
|---|---|
| Admin | Acesso total, configurações de sistema, reajuste em bloco, gestão de usuários. |
| Gerente | Cadastros, movimento, estoque, financeiro, relatórios, **gestão de listas/etiquetas** de Projetos. |
| Operador | Cadastros, movimento (OS/Orçamento), estoque, agendamento, Projetos (uso). |
| Caixa | Venda balcão (PDV) e financeiro de caixa (caixa, fiscal). |

Controles associados: bloqueio por tentativas de senha incorretas, expiração de sessão por inatividade, anti-lockout (não pode desativar/rebaixar a si mesmo).

**RBAC × Plano:** o acesso efetivo a um módulo é `nível de acesso permite **E** módulo está habilitado no plano`. O menu do desktop só mostra itens que passam nos dois filtros; o servidor é a autoridade (§4.5).

---

## 8. Requisitos Não Funcionais

| Requisito | Critério |
|---|---|
| Instalação | Instalador único, execução < 10 min, sem configuração manual de banco. |
| Compatibilidade | Windows 10 e 11, 64 bits. |
| Performance | Listagens (clientes, produtos, OS) respondem em < 1 s com até 50 mil registros. |
| Backup | Rotina de backup do PostgreSQL configurável (local ou rede), documentada. |
| LGPD | Dados pessoais protegidos por RBAC + backup regular. Criptografia de campo é backlog (§10). |
| Fiscal | XML de NF-e/NFC-e autorizados armazenados localmente por ≥ 5 anos, com backup. |
| Disponibilidade | Local API Service registrado como serviço Windows com início automático. |
| Concorrência | 5 estações simultâneas sem lock indevido em OS/vendas diferentes; baixa de estoque com `UPDATE ... WHERE saldo >= qtd` otimista. |
| Licenciamento | Indisponibilidade do RedGest nunca revoga; tolerância de 72 h; modo leitura ao esgotar. |
| Plano | Módulo não habilitado → 403 no servidor e ausência no menu; nunca "tela vazia" enganosa. |

---

## 9. Critérios de Aceite / Plano de Testes (resumo)

**Operacional**
- Criação, edição e fechamento de OS com múltiplos itens.
- Baixa de estoque automática ao fechar venda/OS.
- Fechamento de caixa com conferência de valores.
- Acesso simultâneo de 5 estações sem lock indevido.

**Planos e módulos**
- Plano Essencial: rotas de `projetos`, `financeiro`, `relatorios` e `fiscal` respondem **403**; menu não exibe esses módulos.
- Plano Profissional: `projetos`, `financeiro` e `relatorios` liberados; `fiscal` responde **403**.
- Plano Enterprise: todos os módulos liberados.
- Instalação sem licença: nenhum módulo liberado (cai no fluxo de ativação).
- `entitlements` ausente ou malformado: comportamento seguro (nenhum módulo extra habilitado).

**Licenciamento**
- Ativação online (Contrato C por chave; Contrato B por CNPJ + código).
- Revalidação automática (6 h) detectando revogação/bloqueio/expiração.
- Queda de internet dentro da tolerância — opera normalmente; além de vigência + 72 h — modo leitura.
- Revogação → modo leitura imediato; regularização reativa.
- Limite de ativações excedido → `409`.

**Infraestrutura**
- Reinício da máquina-servidor — serviços voltam; estações reconectam.
- Restore de backup em máquina limpa.

---

## 10. Roadmap de Desenvolvimento

| Fase | Objetivo | Módulos/entregáveis | Plano-alvo |
|---|---|---|---|
| 1 | Fundação | Schema Alembic; Local API Service com healthcheck; auth/sessão; CRUD base; serviços Windows | — |
| 2 | Núcleo operacional | Cadastros, Movimento (OS/Orçamento/PDV), Estoque, RBAC, Agendamento | Essencial |
| 3 | Gestão | Projetos (Kanban Fase 1 + Fase 2), Financeiro, Relatórios | Profissional |
| 4 | Licenciamento | Contrato C (chave de produto) e Contrato B v4.0 (atrás de flag) | — |
| 5 | Fiscal e fechamento | Emissão NF-e/NFC-e via gateway; Pedido de Compra; Anexos de cartão; vínculo cartão↔O.S.; empacotamento; testes de aceitação | Enterprise |

Itens de backlog por plano:

| Item | Motivo do adiamento | Plano-alvo |
|---|---|---|
| Multi-filial ativo | Sem 2ª unidade ainda | Enterprise |
| API de integração | Validar demanda real | Enterprise |
| Criptografia de PII (blind index) | Desproporcional ao porte atual | — (transversal) |
| Assinatura digital (Documenso) | Validar demanda | Enterprise |
| Curva ABC de estoque | Nice-to-have analítico | Profissional |
| Conciliação bancária OFX/CSV | Nice-to-have financeiro | Profissional |
| Réplica/sincronização multi-servidor | Só com filiais remotas | Enterprise |
| Hardware ID / anti-tamper elaborado | Sem evidência de pirataria | — |

---

## 11. Glossário

| Termo | Definição |
|---|---|
| Local API Service | Serviço FastAPI local, único ponto de acesso ao PostgreSQL e de enforcement de RBAC e de plano. |
| Modo Leitura | Estado em que o ERP permite apenas consulta, bloqueando escrita e emissão fiscal, por falta de licença válida. |
| Chave de produto | Código `XXXX-XXXX-XXXX-XXXX` emitido pelo RedGest e digitado na ativação (Contrato C); validado online. |
| Fingerprint da máquina | Hash SHA-256 estável da instalação, enviado na validação para contar as ativações. |
| Contrato C | Modelo de licenciamento do RedGest (`/api/v1/licencas-software/`) por chave de produto, autenticado por HMAC do `Sistema.api_key`. |
| Contrato B | Modelo v4.0 do RedGest (`/api/v1/licencas/`) por CNPJ + código, com credenciais M2M, `grace_deadline` e `entitlements`. |
| Plano | Nível comercial (Essencial/Profissional/Enterprise) que define módulos habilitados e teto de estações. |
| Entitlements | Objeto (`JSONB`) da licença com `plano`, `max_estacoes`, `modulos_habilitados` e afins. |
| Módulo | Unidade vendável do sistema (`cadastros`, `movimento`, `estoque`, `projetos`, `financeiro`, `fiscal`, `relatorios`, ...). |
| Gating de plano | Bloqueio no servidor (403) de rotas de módulos não habilitados, com ocultação correspondente no menu. |

---

## 12. Próximos Passos

1. Validar este PRD (planos, matriz de módulos e enforcement) com quem decide o escopo de negócio.
2. Implementar o gating de plano no backend (dependência de módulo em `deps.py`) e o filtro de menu por plano no desktop.
3. Formalizar o `entitlements` no RedGest (plano + `modulos_habilitados` + `max_estacoes`) para os dois contratos.
4. Acompanhar a depreciação do RedGest: `/licencas-software/` será aposentado (sunset 01/03/2027) em favor de `/api/v1/licencas/` — ver `docs/migracao_redgest_v4.md`.
5. Selecionar gateway fiscal (Focus NFe recomendado) e obter credenciais de sandbox (Fase 5, Enterprise).
