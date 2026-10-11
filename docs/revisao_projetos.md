# Projetos — correções 3.1 e reestruturação 3.2 (Quadro Kanban + Lista)

Documento de entrega da tela de **Projetos** (menu `projetos`), alinhada a
`docs/telas_e_fluxos.md` §§1.3/3.4, ao PRD v2.0/v2.1 e ao `schema.sql`.

> **Sobre os IDs.** O repositório não contém a lista numerada original desta
> tarefa; os itens abaixo usam a âncora **PJ1…PJ8** apenas para rastreio e foram
> reconstruídos a partir do escopo recebido. Cruze com a lista original.

---

## 1. Premissas de escopo (adotadas na largada)

1. **1 projeto = 1 O.S. do tipo `os`.** O `schema.sql` não tem tabela de
   projetos: a tela continua sendo a janela de O.S. (linha `tipo` de
   `OrdemServico`), como já estava.
2. **Etapas do quadro** vêm do enum `status_os` (`aberto`, `aprovado`,
   `producao`, `pronta`, `entregue`, `cancelado`, `convertido`). Decisão
   registrada: **`aprovado` agrupa com `aberto`** na coluna “Aguardando” — o
   orçamento aprovado ainda não entrou em produção.
3. **Calendário** e **arrastar-e-soltar** entre colunas ficam fora desta
   entrega (fase 3 do roadmap) — o quadro é somente leitura.

---

## 2. Componentes

| Arquivo | Papel | Tipo |
| --- | --- | --- |
| `desktop/printgest/ui/kanban.py` | **Novo.** `QuadroKanban` (colunas), `ColunaKanban` (cabeçalho + pilha), `CartaoKanban` (cartão clicável/focável, elidido com tooltip). Sem rede: recebe colunas, uma fábrica de cartões e os dados | compartilhado (novo) |
| `desktop/printgest/ui/modulos/os.py` | `PaginaProjetos` reescrita: alternador **Quadro/Lista**, carregamento por etapa, cartões, “abrir no formulário” | tela |
| `desktop/printgest/ui/modulos/pagina_crud.py` | Guarda `self._filtros_widget` (para ocultar os filtros de status na visão Quadro) | compartilhado (1 linha) |
| `desktop/printgest/ui/theme.py` | QSS do quadro: `#colunaKanban`, `#cartaoKanban`, `#tituloColunaKanban`, `#contagemKanban`, `#tituloCartao`, `#areaQuadro` | compartilhado |
| `desktop/tests/test_projetos.py` | **Novo.** 20 testes (etapas, agrupamento, elide+tooltip, clique→formulário, alternador, estado vazio, modo leitura, 9 combinações de layout) | testes |
| `docs/telas_e_fluxos.md` | Tela de Projetos em §1.3 e atalhos/teclado em §3.4 | doc |
| `docs/evidencias/projetos/` | Capturas **antes/depois** (1280x720, 1366x768, 1920x1080 × 100/125/150%) | evidência |

Nenhum endpoint novo, nenhuma regra de negócio alterada, nenhuma dependência
adicional. O quadro usa exclusivamente `GET /v1/os?tipo=os&status=…` (uma
consulta por etapa; “Aguardando” consulta `aberto` **e** `aprovado`).

---

## 3. Correções 3.1

| ID | Requisito | Status | Observação |
| --- | --- | --- | --- |
| PJ1 | Sem texto cortado sem tooltip | ✅ | Cartão tem `toolTip` com o texto completo; as colunas usam `ElideLabel` (elide + tooltip) |
| PJ2 | Sem **scroll horizontal** e no máx. 1 vertical | ✅\* | Ver §5. O quadro tem **uma** barra vertical única (as colunas crescem juntas) |
| PJ3 | Estado vazio nas listas | ✅ | Coluna mostra “Sem registros” e a Lista herda o estado vazio da base |
| PJ4 | Remover título decorativo | ✅ | Título passou de “Projetos — listagem de O.S. (Kanban na fase 3)” para **“Projetos”** |
| PJ5 | Atalhos reais (F6/F10/Esc, Ctrl+F) | ✅ | Herdados de `PaginaCrud`; **F6 = “Novo Projeto”** (volta para a Lista para mostrar o formulário) |
| PJ6 | Identificador padronizado (“Nº”) | ✅ | Colunas da Lista: **Nº, Cliente, Status, Prazo, Total** |
| PJ7 | Cadastro só por teclado (Tab/Esc) | ✅ | Formulário herdado; no Quadro, `Tab` percorre os cartões e `Enter`/`Espaço` abrem |
| PJ8 | Datas ausentes ⇒ “Sem prazo” (não inventar data) | ✅ | Cartão mostra “Sem prazo · …” quando `data_previsao_entrega` é nulo |

---

## 4. Reestruturação 3.2

| Item | Status | Observação |
| --- | --- | --- |
| Visão **Quadro (Kanban)** | ✅ | Colunas **Aguardando** (`aberto`+`aprovado`), **Em produção** (`producao`), **Prontas** (`pronta`), **Entregues** (`entregue`) |
| Visão **Lista** | ✅ | Grade densa + formulário lateral, idêntica ao restante do sistema |
| Alternador Quadro/Lista | ✅ | Botões `chaveRapida` na barra de título; **Quadro é o padrão** |
| Cartão abre o projeto | ✅ | Clique/`Enter` carrega o registro no **formulário da Lista** (troca a visão) |
| Cartão marcado como **atrasado** | ✅ | Prazo vencido e status ≠ `entregue`/`cancelado` ⇒ badge “Atrasado” |
| Contagem por etapa | ✅ | Badge com o número de projetos de cada coluna |
| Filtros de status **só na Lista** | ✅ | No Quadro as próprias colunas já são os status; os chips ficam ocultos |
| Progresso da O.S. sem arrastar | ✅ (mínimo) | O avanço de status continua pelo botão “Avançar status” do formulário (fluxo `aberto→aprovado→producao→pronta→entregue`) |

Sem calendário e sem drag-and-drop — ver §7.

---

## 5. Layout / testes

- Suíte completa: **198 passed** (`pytest -q`), incluindo
  `desktop/tests/test_projetos.py` (novo, 20 testes).
- O teste de layout roda a página na **largura lógica real** em 1280x720,
  1366x768 e 1920x1080 × 100/125/150% e verifica que o **piso da página cabe** e
  que o **quadro não rola na horizontal** (lateral recolhida, o pior caso real).
- Piso medido da página em Quadro: **726px** (barra de título 686px + margens),
  contra a área de conteúdo de **789px** no pior caso (1280@150%, lateral
  recolhida). A barra de título só cabe porque o botão passou a “Novo Projeto”.

---

## 6. Screenshots (antes/depois)

Versionados em `docs/evidencias/projetos/`:

```
docs/evidencias/projetos/antes/    projetos_antes_<res>_<escala>.png     (9)  — Lista única de O.S.
docs/evidencias/projetos/depois/   projetos_quadro_<res>_<escala>.png    (9)  — Kanban (padrão)
docs/evidencias/projetos/depois/   projetos_lista_<res>_<escala>.png     (9)  — Lista + formulário
```

Resoluções: `1280x720`, `1366x768`, `1920x1080`; escalas: `100`, `125`, `150`.

---

## 7. Fora de escopo / pendências (com motivo)

1. **Calendário** de produção/entregas (Agendamento): exige decisão de widget Qt
   (o próprio roadmap registra isso) e não existe no backend de Projetos.
2. **Arrastar-e-soltar** cartões entre colunas: mudaria status por drag;
   optou-se por manter o avanço explícito pelo formulário (evita alterar regra
   de negócio sem spec).
3. **Orçamentos no quadro:** o quadro lista só `tipo = os`; orçamentos têm a
   página própria (`PaginaOrcamento`). Se quiser “funil único”, é uma decisão de
   produto.
4. **Paginação do quadro:** cada coluna carrega até **200** itens
   (`limit=200`) — suficiente para o volume do MVP; acima disso a coluna fica na
   “primeira página”. Paginação/scroll infinito por coluna fica para depois.
5. **Projetos como entidade própria** (tarefas, checklist, anexos): não existe
   no `schema.sql`; dependeria de migração.

---

## 8. RBAC e regressão

- **RBAC preservado**: Projetos é movimento (nível **Operador**+); nenhum item
  novo de menu, nenhuma rota nova. Em **modo leitura**, o quadro continua
  consultável e as ações de escrita ficam desabilitadas (herdado).
- Sem regressão em cabeçalho, lateral, Início, PDV e Cadastros — a suíte
  completa (198 testes) segue verde e nenhum endpoint foi alterado.
