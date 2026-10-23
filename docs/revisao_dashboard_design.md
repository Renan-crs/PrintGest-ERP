# Revisao de Design — Tela Inicial (Dashboard)

**Versao:** 1.0.0
**Data:** 2026-10-21
**Escopo:** `desktop/printgest/ui/tela_principal.py` (`PaginaInicial`) e tokens em
`desktop/printgest/ui/theme.py`.
**Metodos aplicados:**
- `dickwu/apple-design-skill` — lentes de acessibilidade, convencao de
  plataforma, craft visual, interacao e conteudo (HIG).
- `nextlevelbuilder/ui-ux-pro-max-skill` — `quick-reference.md` (10 categorias de
  regras) e `pro-rules.md` (checklist de entrega).

---

## 1. Contexto

- **Plataforma / framework:** desktop Windows, PySide6 (Qt6), QSS proprio.
- **Produto e audiencia:** ERP de balcao para grafica rapida; operador fica 10 h
  em turno, sob luz fluorescente; leitura rapida de numeros e filas.
- **Artefato auditado:** codigo-fonte (nao screenshot). Contrastes calculados a
  partir dos hex reais do tema, nao estimados.
- **Tese da tela:** responder "como esta o dia?" em 5 segundos — quanto vendeu,
  o que vence, o que esta atrasado — e oferecer o proximo clique.
- **Elemento assinatura:** os cartoes de KPI numerados com subtexto comparativo
  ("ontem: N"), que dao contexto em vez de so o numero solto.

**Veredito:** *Good*. Nenhum achado Critico apos as correcoes. Dois achados Altos
(um de contraste, um de hierarquia de CTA) e um conjunto de Medios de estado
vazio e acessibilidade.

---

## 2. Correcoes aplicadas

### Contraste (Critico na medicao, corrigido)

| Elemento | Antes | Ratio | Depois | Ratio |
|---|---|---|---|---|
| Texto verde "Nenhum item abaixo do minimo" | `#248A3D` sobre branco | **4,40:1** (abaixo de 4,5:1) | `#1B7031` | **6,16:1** |
| Badge de sucesso sobre container | `#248A3D` sobre `#E9F6EC` | **3,95:1** | `#1B7031` sobre `#E3F3E7` | **5,35:1** |

Regra: `quick-reference.md` §1 `color-contrast` e §6 `color-accessible-pairs`
(4,5:1 para texto normal). Confirmado por calculo de luminancia relativa WCAG.

### Hierarquia de acao (Alto)

- **Antes:** os 4 atalhos de "Acesso rapido" eram todos `role="primary"` —
  quatro botoes de acento identicos, sem hierarquia
  (`quick-reference.md` §4 `primary-action`: "cada tela tem so uma CTA primaria").
- **Depois:** apenas o primeiro atalho e primario; os demais usam o novo
  `role="secondary"` (contorno forte, sem preenchimento), subordinados mas ainda
  faceis de achar.

### Estado vazio (Medio)

- **Antes:** "Entregas de hoje" vazio mostrava um item desabilitado dentro da
  lista — um beco sem saida (`quick-reference.md` §8 `empty-states`).
- **Depois:** a lista some e entra um estado vazio com **acao de recuperacao**
  ("Ver Ordens de Servico"), que navega para `/v1/os`.
- **Antes:** o grafico de faturamento vazio dizia apenas "Sem dados no periodo".
- **Depois:** explica a causa e a condicao de aparecimento ("Sem movimentacao no
  periodo — as barras aparecem quando houver vendas ou contas a receber.").

### Cor nao e o unico indicador (Medio)

- **Antes:** entrega atrasada era sinalizada so por texto vermelho
  (`quick-reference.md` §1 `color-not-only`).
- **Depois:** o texto passa a iniciar com "Atrasada <cliente> ..." e o rotulo
  textual carrega o aviso; o vermelho vira reforco, nao transportador unico.
- **Estoque OK:** "Nenhum item abaixo do minimo" ganhou o prefixo `✓`.

### Grafico de faturamento (Medio)

- **Antes:** duas series (Realizado x Previsto) na mesma cor de barra, sem
  legenda, sem valor exato (`quick-reference.md` §10 `color-guidance`,
  `direct-labeling`, `legend-visible`).
- **Depois:** cada serie tem rotulo textual visivel, cores distintas (`barraRealizado`
  = acento cheio; `barraPrevisto` = contorno tracejado + preenchimento leve, para
  diferenciar tambem sem cor) e cada barra expoe o valor exato em tooltip.

### Acessibilidade (Medio)

- Nomes acessiveis adicionados em: cartoes de KPI (`titulo` / `valor` / `detalhe`),
  lista de entregas, containers de serie do grafico e cada barra
  (`quick-reference.md` §1 `voiceover-sr`, `aria-labels`).
- Figuras tabulares (`font-variant` aproximado via familia monoespacada no valor
  do KPI) para a fileira de numeros nao "tremer" ao atualizar
  (`quick-reference.md` §6 `number-tabular`).

### Resiliencia de conteudo

- `_sem_resumo` (falha de rede) agora tambem coloca a lista de entregas no estado
  vazio, evitando deixar dados antigos na tela e esconde/atualiza mensagens
  obsoletas.

---

## 3. O que foi mantido (nao mexer)

- Estrutura em `QScrollArea` com layouts fluidos, sem altura fixa — sobrevive a
  1280x720, 1366x768 e 1920x1080 (coberto por `test_dashboard_layout.py`).
- Separacao por fio de cabelo (`hairline`) em vez de blocos pesados.
- Hierarquia por peso + tamanho, com tracking negativo no titulo.
- RBAC de cards por nivel (vendas todos; a receber gerente+; projetos/entregas/
  estoque operador+).
- Banner nao bloqueante de tolerancia e banner de modo leitura.

---

## 4. Craft notes

- A tela tem ponto de vista: e uma **mesa de situacao**, nao um dashboard
  generico de "cartoes iguais". O subtexto comparativo e o que a distingue.
- Restricao respeitada: nada de emoji como icone estrutural, nada de gradiente,
  nada de sombra dura. O unico emoji e o `⚠`/`✓` em texto, carregando significado
  junto de palavras (permitido; nao e icone de navegacao).
- Um elemento a menos: as quatro CTAs primarias viraram uma primaria + tres
  secundarias. Nenhuma funcionalidade perdida.

---

## 5. Proxy de conformidade (checklist)

Do `pro-rules.md` (adaptado de mobile para desktop):

- [x] Contraste de texto normal >= 4,5:1 (ver secao 2).
- [x] Nenhum emoji como icone estrutural.
- [x] Estados de foco/pressed definidos no QSS, sem deslocar layout.
- [x] Estado vazio com mensagem e acao.
- [x] Cor nao transporta informacao sozinha.
- [x] Rotulos acessiveis em controles e dados.
- [x] Ritmo de espacamento consistente (12 px entre cartoes, 8 px interno).
- [ ] **Pendente:** foco por teclado na lista de entregas (Enter para abrir).
      Hoje o item e clicavel mas sem atalho de teclado documentado.
- [ ] **Pendente:** navegacao por Tab entre as barras do grafico (as barras sao
      informativas; tooltip exige mouse). Alternativa: expor a serie numa tabela
      acessivel sob demanda.

---

## 6. Proximos passos sugeridos

1. Atalho de teclado na lista de entregas (Enter abre a O.S. do item focado).
2. "Legenda interativa": clicar em "Realizado"/"Previsto" alterna a serie.
3. Se a tela crescer, mover as agregacoes do grafico para um endpoint dedicado e
   renderizar com um componente de chart propriamente dito.
