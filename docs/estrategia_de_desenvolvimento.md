# Estratégia de Desenvolvimento — PrintGest ERP

**Versão:** 1.0.0
**Data:** 2026-09-20
**Base:** PRD v2.0, `telas_e_fluxos.md`, design system `fluent_print_erp/DESIGN.md`, mockups da pasta `stitch_print_shop_management_system/`, estado atual do monorepo.

---

## 1. Objetivo

Definir a estratégia de construção do PrintGest ERP (gráfica rápida, até 5 estações, 1 filial) a partir do que já existe no repositório: PRD v2.0 recalibrado, fluxos de telas, design system fechado e 23 mockups de alta fidelidade. O documento organiza o **"o quê construir primeiro"**, **"como portar o mockup para código"** e **"o que é aceitável como pronto"**, reduzindo retrabalho e desvio de escopo.

---

## 2. Diagnóstico: o que já existe

### 2.1 Artefatos na pasta `stitch_print_shop_management_system/`

| Tipo | Conteúdo | Uso na estratégia |
|---|---|---|
| Mockups (23 telas, `code.html` + `screen.png`) | Login, ativação de licença, modo leitura, clientes, produtos/serviços, fornecedores, usuários/RBAC, OS (lista/form), orçamentos→OS, venda balcão (PDV), estoque, kardex, reposição/giro, caixa, contas a pagar, docs fiscais, contingência, vendas/faturamento, inteligência comercial, reajuste em bloco, dados da empresa | Fonte de verdade visual e de interação (atalhos, densidade, badges) |
| `fluent_print_erp/DESIGN.md` | Design system completo: cores (tokens M3/Fluent), tipografia Inter com dígitos tabulares, raios, espaçamentos (grid 4px), densidade, elevacionamento, status tokens | Fonte da paleta e métricas para gerar o QSS/theme do PySide6 |
| `prd_2.0.md` / `telas_e_fluxos.md` | Escopo MVP, arquitetura, RBAC, licenciamento `online_periodic`, fluxos de processo e de navegação | Contrato de escopo e regras de negócio |

### 2.2 Cobertura dos mockups vs. `telas_e_fluxos.md`

Os mockups cobrem **23 telas**, mas o PRD/`telas_e_fluxos` descrevem telas **sem mockup** — é preciso decisão de UI antes de entrar na fase correspondente:

| Sem mockup | Onde entra | Ação |
|---|---|---|
| Funcionários / Vendedores / Atendentes | Cadastros (2.x) | Reaproveitar padrão "Clientes" (lista + formulário), criar mockup |
| Categorias de Produto | Cadastros (2.x) | Lista simples; mockup leve |
| Pedido de Compra (lista + formulário) | Movimento (3.x) | Derivar de "Fornecedores"/"OS"; fluxo de recebimento tem regras próprias |
| Agendamento (calendário/lista) | Movimento (3.x) | Interação nova (calendário) — decisão de widget Qt antes de construção |
| Contas a Receber + baixa | Financeiro (5.x) | Numeração do mockup pula de 5.1 para 5.3 → provável 5.2 ausente = Contas a Receber |
| Plano de Contas | Financeiro (5.x) | Cadastro simples em árvore |
| Extrato do Dia (caixa) | Financeiro (5.x) | Fluxo interno da 5.1 |
| Mais Vendidos / Aniversariantes do Mês | Relatórios (7.x) | Provavelmente dentro da 7.2 (inteligência comercial); validar |

**Recomendação:** manter `mockups/` (já versionado) como canônico e **não** duplicar em `stitch_print_shop_management_system/`. Consolidar o conteúdo da pasta `stitch` (docs embutidos) em `docs/` e remover o duplicado para evitar divergência entre duas cópias.

### 2.3 Estado do monorepo

- **Backend** (`backend/`): FastAPI com apenas `/health`; modelos SQLAlchemy 2.x já escritos (`app/models/`: core, cadastros, movimento, financeiro, fiscal, config, enums) espelhando `schema.sql`. Alembic scaffold iniciado (`alembic.ini`, `alembic/`), sem migrations.
- **Desktop** (`desktop/`): esqueleto PySide6 (`MainWindow`), pacotes `ui/`, `printing/`, `core/` vazios.
- **Scripts** (`scripts/`): `setup_postgres.ps1` (PostgreSQL portátil em `.dev/postgres`, porta 5432) e `redgest_stub.py` (stub do contrato genérico do RedGest — `/api/v1/licencas/*` com `online_periodic`, JWT RS256 e chave de dev persistida em `.dev/redgest_stub_jwt/`, porta 9100).
- **Infra dev**: PostgreSQL 16.10 portátil já operando em `127.0.0.1:5432` (usuário `printgest`, db `printgest`).
- **Git**: commit `Fase 0` (baseline) feito; `alembic/`, `app/models/`, `setup_postgres.ps1` e a pasta `stitch` ainda não commitados.

---

## 3. Diretrizes de engenharia

### 3.1 Arquitetura do backend (regra de negócio 100% servidor)

O Local API Service é o único que acessa o PostgreSQL (D1) e o único que aplica RBAC (D1/D3). Padrão em camadas:

```
app/api/        → routers + schemas Pydantic (contrato HTTP)
app/services/   → regras de negócio (fechar OS, baixar estoque, fechar caixa, converter orçamento)
app/models/     → SQLAlchemy 2.x (já existe)
app/deps.py     → auth, sessão, RBAC, current_user
```

Regras:
- **Toda escrita que altera mais de uma tabela é uma transação** em serviço (ex.: venda → baixa de estoque + lançamento de caixa + conta a receber/`documento_fiscal`).
- **RBAC é aplicado no backend**: middleware/níveis por rota e por recurso; o desktop apenas oculta o menu (usabilidade), nunca confia em menu oculto.
- **Concorrência 5 estações**: evitar locks de linha longos. Estoque reduzido via `UPDATE ... WHERE saldo >= qtd` otimista com retry, sem travar linhas de OS diferentes; testes de acesso simultâneo são critério de aceite.
- **Valores monetários/quantidade** sempre `Decimal` (Pydantic `condecimal` + `NUMERIC`), nunca `float`.

### 3.2 Porta de UI: mockup HTML/Tailwind → PySide6

Os mockups são HTML estático de *referência* — **não** serão embarcados via QWebEngine (pesado, foge do perfil de 5 estações modestas):

1. **Tokens**: extrair cores/tipografia/raios/espaçamento do `DESIGN.md` para um único módulo `desktop/printgest/ui/theme.py` (paleta + métricas), gerando QSS global e constantes para `setStyleSheet`/geometria. Nada de cor "solto" no código.
2. **Componentes reutilizáveis**: `ui/widgets/` com `SearchBar`, `DataTable` (densidade 32px/40px, ordenação, seleção com borda esquerda 3px), `StatusBadge`, `KbdHint`, `ToolbarButton`, `Banner` (modo leitura), `SplitMasterDetail` (lista à esquerda + formulário à direita, padrão em quase todas as telas).
3. **Tipografia tabular**: financeiro, números de OS, peso (gsm), dimensões e timestamps devem usar dígitos tabulares (fonte tabular ou `QFont::setFeatures` equivalente).
4. **Atalhos de teclado são requisito contratual** (ver tabela em §4.5), não finalização opcional.
5. **Shell comum**: janela principal (nível 0, fundo `#F1F5F9`), barra de navegação esquerda (240px), regra de janela com header frameless estilo Fluent, barra de telemetria inferior com badge `127.0.0.1:Online` / `Local API:Offline` e pill de licença (`Licença Ativa (72h OK)` → dias restantes).

### 3.3 Como consumir o backend no desktop

- `desktop/printgest/core/` = client HTTP (httpx) para o Local API Service + armazenamento do token/sessão.
- Todas as listagens usam paginação/busca por parâmetro (`?q=`, offset/limit); alvo < 1s com 50k registros (requisito NFR).
- O único outro acesso aredes do desktop é a impressão via QPrinter (`printing/`).

---

## 4. Roadmap em fases (alinhado ao Roadmap do PRD §7)

Cada fase gera PRs pequenos e testáveis. Ordem **não** troca: fundação antes de telas; núcleo antes de financeiro/fiscal; licenciamento em paralelo possível apenas com o stub.

### Fase 1 — Fundação (em andamento)
- [ ] Gerar migrations Alembic a partir dos models existentes; aplicar no PG portátil; validar contra `schema.sql`.
- [ ] Estrutura `app/api/` + `app/services/` + `app/deps.py`; esquema de resposta padrão (erros PT-BR, códigos HTTP coerentes).
- [ ] **Auth/sessão**: login, `usuario_sessao`, bloqueio por tentativas, expiração por inatividade, nível de acesso no token de sessão.
- [ ] CRUD base de cadastros (clientes, fornecedores, produtos, categorias, funcionários, usuários) — router + schema + testes.
- [ ] Registro do Local API Service e do PostgreSQL como serviços Windows com início automático (mitiga o ponto único de falha).
- [ ] Consolidar `stitch_print_shop_management_system/` (mover docs → `docs/`, remover duplicata).

### Fase 2 — Núcleo operacional
- [ ] Movimento: OS + itens, orçamento + conversão em OS, venda balcão, pedido de compra + recebimento, agendamento.
- [ ] Estoque: kardex via `movimento_estoque`, baixa automática em venda/OS (transação), movimentação manual, reposição, mais vendidos.
- [ ] RBAC efetivo nas rotas (admin/gerente/operador/caixa) com testes.
- [ ] Desktop: shell + telas 1.x (login/ativação/modo leitura), 2.x (cadastros) e 3.x/4.x (movimento/estoque), com atalhos e temas.
- [ ] Decisão de widget p/ agenda (calendário) e criação dos mockups faltantes de cadastros.

### Fase 3 — Financeiro e Fiscal
- [ ] Caixa (abertura, lançamentos automáticos, sangria/suprimento, fechamento com conferência e divergência), contas a pagar/receber + baixa, plano de contas.
- [ ] `documento_fiscal`: emissão NF-e/NFC-e via gateway (Focus NFe como padrão), recebimento de retorno, armazenamento XML/DANFE (≥5 anos), contingência e reenvio.
- [ ] Camada adapter do gateway fiscal: uma interface, diferentes implementações (Focus → PlugNotas/eNotas) sem tocar nas regras.
- [ ] Desktop: telas 5.x, 6.x.

### Fase 4 — Licenciamento (`online_periodic`)
- [ ] Cliente RedGest no Local API Service: ativação (CNPJ + código), troca por `client_id/client_secret`, obtenção e renovação silenciosa do JWT (a cada ~3h), `modo leitura` ao expirar sem renovação, revogação refletida na próxima renovação.
- [ ] Validação contra `redgest_stub` (porta 9100) em dev/CI; contrato de endpoints congelado para homologação com o time do RedGest (§3.4 do PRD). Contrato do stub espelha o plano de generalização (`POST /api/v1/licencas/`, `/ativar`, `/validar`, `/revogar`, `GET /sistemas/{codigo}`) com `online_periodic`, JWT **RS256** e TTL configurável via `REDGEST_STUB_TOKEN_TTL` (para testes rápidos de modo leitura) — chave pública exposta em `/sistemas/{codigo}`.
- [ ] Desktop: badge de telemetria + banner modo leitura (`F9 — Sincronizar Agora`).
- [ ] **Bloqueador externo**: pendência com o RedGest (suporte ao `online_periodic`). Mitigação: fluxo e testes entregues contra o stub, prontos para apontar a URL real.

### Fase 5 — Relatórios e fechamento
- [ ] Relatórios operacionais (vendas por período, clientes top, serviços mais executados, aniversariantes, reposição/giro) + encerramento de dia.
- [ ] Reajuste de preços em bloco com simulação, confirmação por senha e trilha de auditoria (`preco_reajuste_historico`).
- [ ] Impressão (jato, matricial 80 col., cupom 40 col.) via QPrinter.
- [ ] Empacotamento: PyInstaller + Inno Setup com PostgreSQL embarcado; manual de instalação (instalador único, < 10 min, sem setup manual de banco).
- [ ] Testes de aceitação: operacional, licenciamento e infraestrutura (§8 do PRD), incluindo restore de backup em máquina limpa.

---

## 5. Ordem sugerida de PRs (Fase 1 e 2 em detalhe)

1. Migrations Alembic (baseline) → 2. Auth/sessão + RBAC nas rotas → 3. CRUD clientes/fornecedores → 4. Produtos/categorias → 5. Usuários/níveis → 6. OS + orçamento/conversão → 7. Venda balcão + baixa de estoque → 8. Pedido de compra/recebimento → 9. Estoque (kardex/manual/reposição) → 10. Desktop shell + telas 1.x/2.x → 11. Desktop 3.x/4.x.

Cada PR de rota: **modelo → migration → router + schemas → testes → tela PySide6** (quando chegar a vez da fase de UI).

---

## 6. Estratégia de testes e QA

| Camada | Estratégia |
|---|---|
| Backend (unit/integration) | pytest + httpx async; banco de teste dedicado (rodar migrations); casos por serviço: venda→estoque→caixa, conversão orçamento→OS, fechamento de caixa, contas a pagar/receber |
| RBAC | Teste de autorização por nível em cada rota (não apenas presença de endpoint) |
| Licenciamento | Suíte contra o `redgest_stub`: ativação, renovação, janela offline (token expira → modo leitura), revogação |
| Concorrência | 5 estações simuladas (workers paralelos) acessando OS/vendas diferentes sem lock indevido; venda do mesmo último item de estoque convergindo (otimista) |
| Fiscal | Gateway em modo "sandbox"; cenários: autorizada, rejeitada, gateway fora (contingência + reenvio) |
| Desktop | Smokes de abertura de cada tela e navegação pelos atalhos; consistência visual vs. mockup (checklist manual de tokens por tela) |

Definição de pronto ética: **nenhum PR de tela entra sem os atalhos de teclado previstos no mockup** e sem o badge de telemetria/licença presente.

---

## 7. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| RedGest sem suporte a `online_periodic` (pendência §3.4) | Contrato congelado via `redgest_stub`; zerar dependência de homologação para avançar Fases 1–3 e 5; só o tunning final precisa da URL real |
| Ponto único de falha (máquina-servidor) | Serviços Windows com início automático, healthcheck de reconexão nas estações, documentação; aceito conscientemente no porte (NFR) |
| Conflito de porta 5432 (PG global vs. portátil) | PG portátil preso a `127.0.0.1`; documentar no manual; se o cliente tiver PG global, decidir porta alternativa de forma configuravel |
| Escopo novo nas telas sem mockup (agenda, pedido de compra, contas a receber, plano de contas) | Decidir tardiamente essas telas (conforme fase), mas **derivar dos padrões existentes**; mockup rápido antes de codificar |
| Divergência `mockups/` vs `stitch_print_shop_management_system/` | Manter uma única fonte canônica; consolidar na Fase 1 |
| Regras em duas camadas (UI + backend) | Regra de negócio só em `services/`; desktop é cliente fino; revisão de PR verifica isso |

---

## 8. Definição de Pronto (DoD)

Um item (rota ou tela) só é "pronto" quando:
1. Rota + schemas Pydantic + service transacional (se multi-tabela) + testes passando.
2. RBAC aplicado e testado por nível.
3. Tela PySide6 fiel ao mockup (tokens do theme, densidade, atalhos do mockup, estado de telemetria/licença).
4. Rotina de busca rápida presente em listagens (requisito transversal).
5. Deployável no PG portátil via migration Alembic — sem SQL manual.
6. Rodando em rede: 1 estação-servidor + estação-cliente reais (quando a infra da Fase 1 estiver de pé).

---

## 9. Decisões em aberto (próximos passos)

1. Escolher gateway fiscal definitivo (Focus NFe recomendado) e obter credenciais de sandbox.
2. Homologar `online_periodic` com o time do RedGest (paralelo ao desenvolvimento).
3. Definir quem/dados geram os mockups das telas faltantes (agenda, pedido de compra, contas a receber, plano de contas, funcionários, categorias).
4. Definir padrão de testes do desktop (QTest) e CI (runner local com PG portátil).