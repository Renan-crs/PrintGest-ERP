# Financeiro — implementação do módulo (release 0.2)

Documento de entrega do menu **Financeiro** (id `financeiro`), alinhado a
`docs/telas_e_fluxos.md` §§1.5/2.4, ao PRD v2.0/v2.1 (§1.3, RBAC §5) e ao
`schema.sql` (tabelas `caixa`, `movimento_caixa`, `conta_receber`, `conta_pagar`,
`plano_contas`).

> **Sobre os IDs.** O repositório não contém a lista numerada original desta
> tarefa; os itens abaixo usam a âncora **FN1…FN8** apenas para rastreio e foram
> reconstruídos a partir do escopo recebido. Cruze com a lista original.

---

## 1. Premissas de escopo (adotadas na largada)

1. **As contas a receber/pagar não são criadas pela tela.** Elas nascem dos
   documentos de movimento (O.S., venda balcão, pedido de compra) e dos
   adiantamentos/sinais — conforme o `schema.sql` (`conta_receber.venda_balcao_id`,
   `ordem_servico_id`; `conta_pagar.pedido_compra_id`). A tela Financeiro **lista
   e dá baixa**; não há “Novo título”.
2. **Caixa é por usuário e por filial.** `GET /caixa/atual` devolve o caixa
   **aberto do usuário logado** na filial corrente.
3. **RBAC não hierárquico (PRD §5).** `operador` tem rank maior que `caixa`, mas
   **não** acessa Financeiro. Por isso o router usa uma checagem por lista de
   perfis (`_perfis`), e não o `require_nivel` por rank.
4. **Nasceu endpoint novo** (`/v1/financeiro/*` e `/v1/plano-contas`) porque as
   tabelas existiam no `schema.sql`/migração baseline e o módulo estava no
   roadmap; nenhuma regra de negócio existente foi alterada.

---

## 2. Componentes

| Arquivo | Papel | Tipo |
| --- | --- | --- |
| `backend/app/schemas/financeiro.py` | **Novo.** Schemas de caixa, movimentos, contas e plano de contas | backend (novo) |
| `backend/app/services/financeiro_service.py` | **Novo.** Regras: abrir/fechar caixa (esperado × informado → diferença), movimentos (só sangria/suprimento manual), listagem e **baixa** (total/parcial) de contas | backend (novo) |
| `backend/app/api/financeiro.py` | **Novo.** Router `/v1/financeiro` + CRUD `/v1/plano-contas`; registrado em `app/api/__init__.py` | backend (novo) |
| `desktop/printgest/ui/modulos/financeiro.py` | **Novo.** `PaginaCaixa`, `PaginaContas` (+`PaginaContasReceber`/`PaginaContasPagar`), `PaginaPlanoContas`, `PaginaFinanceiro` (host de sub-abas) | tela (novo) |
| `desktop/printgest/core/api.py` | Métodos `caixa_atual`, `abrir_caixa`, `fechar_caixa`, `movimento_caixa`, `extrato_caixa`, `baixa_conta` | compartilhado |
| `desktop/printgest/ui/modulos/__init__.py` | `criar_pagina` mapeia `financeiro` → `PaginaFinanceiro` e os ids internos `caixa`/`contas_receber`/`contas_pagar`/`plano_contas` | compartilhado |
| `desktop/tests/test_financeiro.py` | **Novo.** 8 testes de UI (host por perfil, caixa, baixa, plano de contas) | testes |
| `backend/tests/test_financeiro.py` | **Novo.** 10 testes de backend | testes |
| `docs/evidencias/financeiro/` | Capturas **antes/depois** (1280x720, 1366x768, 1920x1080 × 100/125/150%) | evidência |

**Reuso:** as telas de contas e de plano de contas herdam `PaginaCrud` (grade
densa + formulário lateral + atalhos F6/F10/Esc + modo leitura). Nenhum
componente compartilhado precisou ser alterado para este módulo.

---

## 3. Backend (novo) — endpoints e RBAC

| Método | Rota | Perfis | Observação |
| --- | --- | --- | --- |
| `GET` | `/v1/financeiro/caixa/atual` | caixa, gerente, admin | Caixa aberto **do usuário** (ou `null`) |
| `POST` | `/v1/financeiro/caixa/abrir` | caixa, gerente, admin | 409 se já houver caixa aberto |
| `GET` | `/v1/financeiro/caixa/{id}/extrato` | caixa, gerente, admin | Movimentos paginados (`limit`≤500) |
| `POST` | `/v1/financeiro/caixa/{id}/movimento` | caixa, gerente, admin | Só `sangria`/`suprimento`; 409 se fechado |
| `POST` | `/v1/financeiro/caixa/{id}/fechar` | caixa, gerente, admin | Grava `valor_esperado`, `valor_informado`, `diferenca` |
| `GET` | `/v1/financeiro/contas-receber` | **gerente, admin** | Filtros `q` (descrição/cliente) e `status_conta` |
| `POST` | `/v1/financeiro/contas-receber/{id}/baixa` | **gerente, admin** | Baixa total/parcial; 409 se paga/cancelada |
| `GET` | `/v1/financeiro/contas-pagar` | **gerente, admin** | Filtros `q` (descrição/fornecedor) e `status_conta` |
| `POST` | `/v1/financeiro/contas-pagar/{id}/baixa` | **gerente, admin** | Idem |
| CRUD | `/v1/plano-contas` | **gerente, admin** | `crud_factory`; busca por `codigo`/`nome`, filtro `tipo` |

As contas a receber/pagar usam `_contas_*_query` com `outerjoin` em
`Cliente`/`Fornecedor` para trazer `cliente_nome`/`fornecedor_nome` na listagem.

---

## 4. Telas (front-end)

### 4.1 Host `PaginaFinanceiro`

- Barra de título **“Financeiro”** + alternador de sub-abas (`chaveRapida`, um
  checkado por vez), reaproveitando o padrão visual do resto do sistema.
- Sub-abas por perfil (mesma regra do menu):
  - **caixa** → vê apenas **Caixa**;
  - **gerente/admin** → **Caixa**, **Contas a Receber**, **Contas a Pagar**,
    **Plano de Contas**.
- A troca de aba remove/reinsere o widget central no layout (sem `QStackedWidget`,
  mesmo padrão de Projetos), chamando `deleteLater()` na página anterior.

### 4.2 `PaginaCaixa` — Abertura / Extrato / Fechamento

| Estado | Painel direito | Rodapé da grade |
| --- | --- | --- |
| **Sem caixa** | form de **Abertura** (valor + observações) e botão **Abrir Caixa (F6)** | extrato vazio |
| **Caixa aberto** | form de **Movimento** (tipo/valor/descrição, **F7**) + **Fechamento** (valor informado, **F9**) | extrato paginado |

- Badges no topo: **SEM CAIXA**/**CAIXA ABERTO** e **Saldo: R$ …**
  (`saldo_atual` = abertura + entradas − saídas, calculado no backend).
- Extrato: **Data/Hora · Tipo · Descrição · Valor**, com o valor prefixado por
  `+`/`-` e formatado em R$.
- Fechamento com divergência pede confirmação e informa a diferença conferida.
- **Modo leitura** (licença): desabilita Abrir/Lançar/Fechar; extrato continua
  consultável.

### 4.3 Contas a Receber / Contas a Pagar

- Herdam `PaginaCrud` como **consulta**: grade densa (Nº, Descrição, Cliente/
  Fornecedor, Vencimento, Valor, Pago, Status), busca e chips de filtro por
  status (Todas/Abertas/Pagas/Canceladas, filtrados no servidor).
- **Formulário sempre desabilitado** — é leitura; a única escrita é **Dar Baixa**.
- Ação extra no rodapé **Receber/Pagar (F9)** abre um diálogo com **valor,
  data e observações**; só habilita para títulos `aberta`.
- Campos de CRUD (Novo/Salvar/Cancelar) ficam ocultos/desabilitados; os atalhos
  F6/F10 não são instalados nesta tela (só **F9** = baixa).

### 4.4 Plano de Contas

- CRUD completo (`PaginaCrud`): **Código, Nome, Tipo (Receita/Despesa), Ativo**;
  busca por código/nome e filtro por tipo. Atalhos F6/F10/Esc herdados.

---

## 5. Requisitos de aceite (mesmo padrão dos Cadastros/Projetos)

| ID | Requisito | Status | Observação |
| --- | --- | --- | --- |
| FN1 | Sem texto cortado sem tooltip | ✅ | Títulos/painéis usam `ElideLabel`; a grade elide com tooltip nativo |
| FN2 | Sem **scroll horizontal** e no máx. 1 vertical | ✅ | Ver §6 — `h=0` em todas as combinações |
| FN3 | Estado vazio nas listas | ✅ | Extrato mostra “Sem movimentos…”; grades herdam o estado vazio da base |
| FN4 | Operação só por teclado (Tab/Esc) | ✅ | Formulários com Tab lógico; diálogo de baixa com Cancelar (Esc) |
| FN5 | Sem conflito de atalhos globais | ✅ | Caixa: F6/F7/F9; Contas: só F9; Plano: F6/F10/Esc (global) |
| FN6 | Valor monetário formatado | ✅ | `formatar_moeda` na grade e nos diálogos |
| FN7 | Datas ausentes não inventadas | ✅ | `formatar_data_iso` devolve vazio/“—” |
| FN8 | RBAC preservado e reforçado | ✅ | Ver §8 |

---

## 6. Layout / testes

- Suíte **desktop**: **206 passed** (`pytest -q`), incluindo
  `desktop/tests/test_financeiro.py` (novo, 8 testes).
- Suíte **backend**: verde, incluindo `backend/tests/test_financeiro.py`
  (novo, 10 testes).
- Verificação de layout sem imagens (`.dev/check_layout_financeiro.py`): mede as
  **scrollbars reais** de `caixa`, `contas_receber`, `contas_pagar`,
  `plano_contas` e do **host**, em 1280x720 / 1366x768 / 1920x1080 × 100/125/150%.
  Resultado: **`h_tab=0` e `h_form=0` em todas as 45 combinações** — nenhuma
  barra horizontal.

---

## 7. Screenshots (antes/depois)

Versionados em `docs/evidencias/financeiro/`:

```
antes/    financeiro_antes_<res>_<escala>.png          (3)  — placeholder "em construção"
depois/   financeiro_caixa_<res>_<escala>.png          (9)  — Abertura/Extrato/Fechamento
depois/   financeiro_contas_receber_<res>_<escala>.png (9)  — lista + baixa
depois/   financeiro_contas_pagar_<res>_<escala>.png   (9)  — lista + baixa
depois/   financeiro_plano_contas_<res>_<escala>.png   (9)  — cadastro
```

Resoluções: `1280x720`, `1366x768`, `1920x1080`; escalas: `100`, `125`, `150`.
Geradas por `.dev/snapshot_financeiro.py` (dados de exemplo com nomes longos,
caixa aberto e extrato).

---

## 8. RBAC e regressão

- **Menu v2.1:** item `financeiro` visível a `admin`, `gerente` e `caixa`
  (inalterado). O backend reforça com `403` via `_perfis(...)`.
- **Não hierárquico:** `operador` não abre Financeiro mesmo com rank acima de
  `caixa`; contas e plano de contas exigem **GERENTE+**.
- **Modo leitura (licença):** toda escrita (abrir/lançar/fechar caixa e dar baixa)
  fica desabilitada; consulta preservada.
- **Sem regressão** em cabeçalho, lateral, Início, PDV, Cadastros e Projetos — a
  suíte completa segue verde. Nenhum endpoint existente foi alterado.

---

## 9. Fora de escopo / pendências (com motivo)

1. **Emissão de NF-e/NFC-e** e integrações fiscais não pertencem a Financeiro —
   ficam no módulo **Fiscal** (sem gateway de emissão disponível).
2. **Criação/edição de títulos** por esta tela: as contas nascem dos documentos
   de movimento (regra do `schema.sql`); criar títulos “na mão” exigiria nova
   regra de negócio fora da spec.
3. **Conciliação bancária / importação de extrato OFX:** não há tabela nem spec;
   dependeria de migração.
4. **Rateio por plano de contas / DRE:** o plano de contas é cadastrável, mas
   relatórios contábeis (DRE, fluxo de caixa) não estavam no escopo desta rodada.
5. **Fechamento automático de caixa** no fim do expediente: hoje é manual (a
   spec descreve o fechamento pelo operador).
