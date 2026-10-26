# Análise do PRD v3.0 — PrintGest ERP (Gráfica Rápida e Pequena Gráfica)

**Data:** 26/10/2026 · **Base:** PRD v3.0 (rascunho para validação) × código atual
(`main`, 26/10/2026) × PRD v2.2 × lente de design (frontend-design skill,
traduzida para o stack desktop). **Veredito:** o documento está maduro e
coerente; a regra VF→CP→VO está correta e testável; há **1 ajuste de redação
matemática**, **2 correções de "alegação de existência"** (uma delas minha),
**1 lacuna de arquitetura que o M0 presume pronta e não está** e **1 conflito
estratégico (D-01) a decidir com critério explícito**. Recomendo validar após
as correções da seção 8.

---

## 1. O que o código real confirma hoje (verificação das alegações)

O PRD diz preservar o existente e listar o que é novo. Verificação item a item
contra `backend/app` e `desktop/printgest`:

| Alegação do PRD | Realidade no código | Veredito |
| --- | --- | --- |
| "Caixa (abertura, sangria, fechamento)" entra no Essencial | **O módulo de caixa já existe e está completo no backend**: modelos `Caixa`/`MovimentoCaixa` e rotas `abrir/extrato/movimento/fechar` com RBAC próprio (`app/api/financeiro.py`) | ✅ correto — mas é **ajuste de matriz, não build**. O que falta é **integração PDV↔caixa** (vender com caixa fechado — pendência D4 da revisão do PDV). *Corrige afirmação anterior minha na revisão do PDV de que "não há módulo de caixa": há, sim — não há o vínculo com a venda balcão* |
| "Contas a receber simples" no Essencial | `ContaReceber` + rota de **baixa** já existem (`financeiro.py`) | ✅ existe — M0 aqui é só matriz/planos |
| "`pedido_compra` já existente" (3.7) | `PedidoCompra` + `PedidoCompraItem` existem (`movimento.py`) | ✅ correto |
| "Fiscal parcial" preservado | `app/api/fiscal.py` é **consulta** de documentos; emissão é nova | ✅ correto |
| "Projetos/Kanban preservado" com versão otimista | Existe, com `versao`/409 — **só em Projetos** | ✅ — e o NFR de concorrência do v3 pede o mesmo em orçamento/OS (não existe lá; ver §4) |
| "`orcamento_item` ganha `tipo`…" (§5) | A tabela real chama-se `ordem_servico_item` (`OrdemServicoItem`); orçamento é `OrdemServico.tipo = orcamento`, com `orcamento_origem_id` | ⚠️ mapear nomes: o §5 deve citar a tabela real (ou renomear explicitamente em migração aditiva — não recomendado agora) |
| Decimal/NUMERIC "sempre, nunca float" (1.2) | Colunas são `Numeric(14,2)`/`Numeric(12,3)` ✅, **porém anotadas como `Mapped[float]`** (`movimento.py:88-90,141-145`) | ⚠️ a coluna está certa; a anotação mente e induz `float` em código novo (o PRD v3 aumenta a superfície de cálculo — saneamento recomendado no M1) |
| "Plan gating aplicado no servidor" (1.2, regra herdada do v2.2) | **Não existe hoje**: nenhuma rota/middleware consulta `entitlements.modulos_habilitados`; o `entitlements` atual carrega apenas `primeira_ativacao`/`limite_ativacoes`/`ativacoes_realizadas` | ❌ **lacuna central** — o M0 presume pronta uma coisa que precisa ser construída (ver §3) |
| Licenciamento online-first, tolerância 72 h, modo leitura | Implementado e validado em campo (Contratos B/C, RedGest real) | ✅ |

## 2. A matemática VF→CP→VO está correta — com duas precisões

Verificado com `Decimal` e `ROUND_HALF_UP` (script da análise):

| VF | CP (VF×2,30) | VO (CP×1,06) | PRD diz | ✓ |
| --: | --: | --: | --: | :-: |
| 100,00 | 230,00 | 243,80 | 243,80 | ✅ |
| 87,35 | 200,91 | 212,96 | 212,96 | ✅ |

**Precisão 1 — arredondamento:** 87,35 × 2,30 = **200,905**. Com o padrão do
Python (`ROUND_HALF_EVEN`, "banker's") o resultado seria **200,90** e o
exemplo do PRD quebraria. O PRD acerta ao exigir "meio para cima"; a
implementação precisa de `quantize(..., ROUND_HALF_UP)` **explícito** — e o
exemplo 87,35 deve virar caso de teste fixo (o PRD já o prevê; mantenham-no
exatamente por esse motivo).

**Precisão 2 — "equivale a VF × 2,438" é ≈, não =:** com arredondamento
intermediário do CP, a fórmula sequencial e a direta divergem em casos de
borda (VF 0,05 → sequencial **0,13**, direta **0,12**; verificado). Para
valores reais de fornecedor a coincidência é quase sempre, mas não é garantida.
Recomendação: trocar "equivale" por "aproximadamente" e declarar que **a
fórmula normativa é a sequencial** (CP arredondado antes do VO), com o teste de
paridade rodando sobre a sequencial.

**Q-01 (markup × margem):** se os 6% fossem **margem sobre o preço final**, a
fórmula seria `VO = CP ÷ 0,94` → 244,68 (≠ 243,80) e 213,73 (≠ 212,96).
Diferença de ~0,4% que compõe ao longo do mês. A interpretação assumida
(acréscimo/markup) é a mais comum em gráfica — **confirmar com o responsável
com esses dois números na mesa** antes de implementar.

## 3. A lacuna central: gating por plano não existe no servidor

A regra "módulo não habilitado responde `403` no servidor" é o coração do
modelo comercial — e hoje **nenhuma rota checa módulos**; o `entitlements`
persistido nem possui a chave. Consequências para o plano:

1. **M0 precisa incluir o mecanismo**: dependência FastAPI por módulo
   (`Depends(exigir_modulo("custos"))`) lendo `licenca.entitlements.modulos`,
   aplicada transversalmente como o middleware de modo leitura já faz
   (padrão já provado no código).
2. **Dependência externa — RedGest**: os `entitlements` com módulos precisam
   ser **emitidos pelo RedGest** na validação/ativação. É o mesmo padrão da
   `api_key` do Contrato C, que ficou bloqueada semanas à espera de
   provisionamento. Incluir no plano do M0: combinar o formato do payload
   (`modulos: [...]`, `plano: "essencial"|"profissional"|"enterprise"`,
   `max_estacoes`) com o RedGest **antes** de codificar o gating, e manter um
   fallback determinístico (sem `modulos` no entitlements = nenhum módulo
   extra, como o PRD já manda: "ausente ou malformado não libera").
3. **Plano atual do piloto**: a licença PARCERIA ativada em campo hoje não
   carrega módulos — a emissão nova precisa revalidar a licença existente sem
   derrubar o piloto (a revalidação de 6 h resolve sozinha; testar).

## 4. Outros achados estruturais

- **409/controle otimista em orçamento e OS** (NFR de concorrência): existe
  apenas em Projetos. O orçamento vira o registro mais concorrido da tela com
  as cotações (atendente + gerente editando) — incluir `versao` + 409 no M1,
  não no fim.
- **Snapshot + recálculo explícito** (3.2.1): muito bem especificado; é o que
  protege o histórico contra mudança de parâmetro. Manter.
- **Confidencialidade (3.2.3)**: o mais forte e correto trecho do PRD —
  "omitir, não ocultar" é a única arquitetura segura. Na implementação:
  **schemas distintos por permissão** (`CotacaoOut` × `CotacaoInternaOut`) e
  nunca `response_model_include`; o teste de varredura rotas×perfis×PDF do
  aceite vira CI. O requisito de que quem lança cotação sem
  `ver_custo_terceiro` perca o VF após salvar é a parte mais sutil — exige
  schema próprio e vale um teste dedicado.
- **Auditoria append-only** (`log_campo_sensivel`): nova tabela; nada contra.
- **D-03 (links públicos)**: coerente com "Local API Service nunca exposto".
  Dependência externa de hospedagem (relay no RedGest ou serviço dedicado) —
  sugerir **fallback de aprovação presencial** (cliente assina na tela do
  atendente) para o M3 caso o relay atrase, para não bloquear o módulo `arte`.
- **Roadmap — M0 × M1**: "M1 antes de qualquer outra entrega" contradiz o M0
  listado antes. Recomendo a redação: "M0 é pré-requisito imediato de M1 e
  pequeno (matriz + gating + integração caixa); M1 é a primeira entrega de
  valor". É o que a tabela já transmite.
- **`relatorios` no Profissional**: esclarecer que o **Início (dashboard
  operacional)** permanece para todos os planos — o que sobe é o relatório
  **gerencial** (margem, DRE etc.), senão a leitura é ambígua.
- **Matriz de planos**: verificada contra o v2.2 — as três correções (caixa e
  receber no Essencial; fiscal no Profissional; motor de preço + orçamento
  com fornecedor no Essencial) são **justas e bem argumentadas**. A validação
  de dependência entre módulos na emissão do entitlements é boa regra
  ("compras sem financeiro" não existe).

## 5. D-01 (plataforma) — o conflito estratégico a decidir com critério

O v2.3 mandava migrar para WPF/.NET 10 **na fase M1**; o v3 propõe **M0–M2 na
plataforma atual (Python/FastAPI/Qt) e decidir depois**. Análise honesta:

- **A favor da proposta v3** (recomendo aceitar): M1 é o núcleo comercial e a
  regra de negócio específica do cliente — congelá-lo durante uma migração de
  stack é o pior momento; o valor entregue fica visível já no piloto real; a
  base atual está estável (247 backend + 339 desktop testes verdes, instalador
  validado em campo, licenciamento funcionando contra o RedGest real).
- **Custo conhecido**: cada módulo em Qt amplia a superfície a portar. O
  `docs/design_tokens.md` (tokens claro/escuro + mapeamento WPF) e o padrão de
  telas revisadas por critérios reduziram esse custo — a migração de tela
  vira tradução de tokens + layout, não redescoberta.
- **Critério de saída explícito** (falta no PRD): "ao fim de M2, decidir a
  migração com base em (a) nº de telas/módulos entregues, (b) custo de
  manutenção medido, (c) aderência do WPF ao apontamento touch (D-04)".
  Registrar no PRD para a decisão não virar eterna.

## 6. Lente de design (frontend-design) traduzida para este stack

A skill é orientada a web, mas seus princípios carregam — e o app já pratica
boa parte (design system + tokens, contraste medido, estados vazios como
convite à ação, motion deliberado de 160 ms, microcopy PT-BR). Aplicação às
**telas novas do §4**, com três destaques da skill:

1. **"Ground in the subject matter"**: as telas do M1 (cotações pendentes,
   precificação) devem parecer de **gráfica**, não de SaaS genérico — o
   vocabulário é VF/cotação/faixa/piso; a lista de "Aguardando cotação" é uma
   **fila de chão de fábrica** (prazo/validade são o tempo do ofício), não um
   CRUD. Isso informa densidade, ordem das colunas (prazo antes de valor) e
   microcopy.
2. **Evitar os "tells" genéricos** que a skill lista — dois tocam no QSS
   atual: *eyebrows em caixa-alta* (nosso `labelForm` é caixa-alta) e *SaaS-card
   kit* (raio único em tudo). Não mudar agora (design system consolidado e
   medido), mas nas **telas novas**: usar `rotuloCampo` (sentence case, 13/600)
   como na Ativação, e variar hierarquia (o bloco de total/vencedor da cotação
   é uma *decisão*, não mais um card).
3. **"Spend boldness in one place"**: na tela de comparativo de cotações, o
   elemento memorável é a **linha vencedora** (fornecedor escolhido) — um
   destaque deliberado; todo o resto quieto. Na visão do cliente: um só
   número importa (total) — hierarquia já praticada no PDV.
4. **Processo**: cada tela nova do §4 entra com o mesmo rito da Ativação/PDV
   (critérios de aceite de UI, contraste medido ≥ 4,5:1, screenshots por
   resolução, estados vazios por módulo `403` incluído) — usando
   `docs/design_tokens.md` como fonte única.

## 7. Q-02 a Q-04 e D-02/D-04/D-05 — recomendações rápidas

| Item | Recomendação |
| --- | --- |
| **Q-02** (VF inclui frete/impostos?) | Manter **campo único** (assumido) + observação livre no lançamento da cotação registrando a composição. Se houver registro recorrente de divergência, promover a campo no M2 |
| **Q-03** (cliente vê só total) | Manter — coerente com a confidencialidade; o documento do cliente é "proposta" (descrição + total), nunca orçamento interno |
| **Q-04** (% por fornecedor/serviço) | Prevista como sobrescrita — **escopo M1: global apenas**; sobrescrita no M2 (evita inflar o núcleo) |
| **D-02** (licença C++) | Concordo com o PRD: opcional, sem evidência de pirataria; o modo leitura + DPAPI já responde |
| **D-04** (apontamento) | QR na OS impressa + tela desktop simples no M4 (como proposto); touch web só após D-01 |
| **D-05** (produto × serviço) | Confirmado: **bloqueia modelagem** — validar com contador antes do M5, não antes do M1 (não trava o orçamento com fornecedor) |

## 8. Correções sugeridas antes de marcar "validado"

1. §5/3.2: trocar `orcamento_item` por `ordem_servico_item` (ou nota de
   renome) e descrever o orçamento como `OrdemServico.tipo=orcamento`.
2. §3.2.1: "equivale a VF × 2,438" → "aproximadamente (a fórmula normativa é
   a sequencial, com CP arredondado antes do VO)".
3. §8.3: redação M0/M1 (M0 como pré-requisito imediato de M1).
4. §2: nota "Início/dashboard operacional disponível em todos os planos;
   `relatorios` refere-se aos gerenciais".
5. §9/D-01: acrescentar critério de decisão com métricas ao fim de M2.
6. §5: nota de saneamento `Mapped[float]` → `Mapped[Decimal]` nas colunas
   `Numeric` (pré-M1, para o motor de preço não herdar a anotação errada).
7. §3.2.1: explicitar `ROUND_HALF_UP` como modo (o texto diz "meio para cima";
   a implementação precisa saber que o default do Decimal é banker's).
8. M0: incluir "formato do `entitlements.modulos` acordado com o RedGest" como
   entregável explícito (a lição da `api_key`).

## 9. Checklist de validação para o responsável

1. **Q-01**: 130% + 6% são markup sobre a base? (mostrar 243,80 vs 244,68).
2. **Q-02**: VF inclui frete/impostos? (assumido sim).
3. **Q-04**: sobrescrita de % por fornecedor/serviço entra no M1 ou M2?
   (recomendo M2).
4. **D-01**: aceitar M0–M2 em Python com critério de decisão ao fim de M2?
5. **D-03**: relay no RedGest × serviço dedicado × fallback presencial no M3?
6. Matriz de planos: fiscal no Profissional e caixa no Essencial confirmados?
7. Piso de preço e permissão de Gerente (3.1): limite padrão inicial?

---

*A análise verificou os exemplos monetários com `Decimal`/`ROUND_HALF_UP`
(script de referência em `docs/analise_prd_v3.md` §2), as alegações de
existência contra `backend/app` e a matriz de planos contra `docs/prd_2.2.md`
§3.2/3.3. Não houve implementação de código nesta análise.*
