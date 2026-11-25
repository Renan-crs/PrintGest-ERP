# Variações de produtos e serviços no PrintGest

Nov 23, 2026 · @Renan Silva

**Guia de modelagem e de fluxo para o desenvolvimento** · Status: proposta para validação · Base: exemplo de impressão informado pelo negócio e regras de plataforma do [PRD PrintGest v3.3](https://claude.ai/artifact/AxpTy5VZx11imZLqgARJjs).

---

## Status de implementação (baseline v0.5.30 — 24/11/2026)

> **Como ler:** este guia continua sendo uma **proposta para validação**. Os
> marcadores abaixo apenas informam o ponto de partida no produto atual; o texto
> das seções seguintes foi preservado. Legenda: ✅ implementado · 🚧 parcial ·
> ⬜ proposta (não implementado).
>
> **Diferença estrutural relevante:** o modelo hoje **não** tem entidades
> `eixo_variacao`/`opcao_variacao`. A variação é uma linha de `produto` com
> `produto_pai_id`, `sku`, `uuid` e três atributos fixos (`tamanho`, `marca`,
> `cor`), com UNIQUE por `(filial, pai, atributos)`. O preço legado segue em
> `produto.preco_venda` (`Numeric(14,2)`) — agora convive com as regras
> persistidas da V1. Serviço não gera variação e não controla estoque; não
> existe entidade `insumo` separada (o insumo reaproveita `produto`). Ou seja:
> **V0, V1 e V2 estão em andamento** (matriz, SKU, uuid, estoque por variante e
> modo leitura; motor de preço v0.5.31, integração em venda/OS v0.5.32;
> tabelas/regras com vigência e snapshot v0.5.33; fichas de consumo, custo,
> margem e baixa real v0.5.34); **V3–V4 são proposta**, com ilhas isoladas de
> reajuste em bloco e outbox de sincronização.
>
> **Migration V1 aplicada ao Neon:** `e5f6a7b8c9d0` (backup em branch — ver
> `docs/migration_regras_preco_v1.md`). **Migration V2 pendente de autorização:**
> `f6a7b8c9d0e1` (`ficha_consumo`, `os_item_consumo`), aditiva.

| RF | Tema | Status | O que já existe / o que falta |
| --- | --- | --- | --- |
| RF-VR-01 | Produto vs serviço e unidade de venda | ✅ | `tipo` e `unidade` no cadastro; serviço bloqueado de estoque. O campo se chama `unidade`, não `unidade_venda` |
| RF-VR-02 | Eixos e opções modelados | 🚧 | Três atributos fixos na tela (tamanho, marca, cor); sem entidades de eixo/opção, `ordem`, `obrigatorio` ou modificadores |
| RF-VR-03 | Variações por combinação, chave canônica e SKU | 🚧 | Combinações informadas linha a linha (não produto cartesiano); SKU e uuid existem; a "chave canônica" é o UNIQUE `(filial, pai, atributos)`. SKU é único por filial, não global |
| RF-VR-04 | Aviso de explosão > 100 variações | ⬜ | Sem limite funcional; só `max_length=200` do payload e confirmação genérica na UI |
| RF-VR-05 | Compatibilidade e `COMBINACAO_INVALIDA` | ⬜ | Nenhuma tabela de compatibilidade nem esse código de erro |
| RF-VR-06 | Estados rascunho/publicado/inativo | 🚧 | Só `ativo` (soft delete do pai desativa as filhas); sem rascunho/publicação nem bloqueio por preço/ficha faltando |
| RF-VR-07 | Cálculo de preço no servidor (7.1) | 🚧 | Motor integrado em venda/orçamento/OS; com regra vigente no banco o servidor calcula e ignora o unitário enviado (v0.5.33) |
| RF-VR-08 | Precedência cliente/filial/padrão e `PRECO_NAO_CADASTRADO` | 🚧 | `tabela_preco`/`regra_preco` persistidas com precedência cliente → filial → padrão e erro `PRECO_NAO_CADASTRADO`; falta expor o cadastro na UI do desktop |
| RF-VR-09 | Faixas de quantidade | 🚧 | `TODA_A_QUANTIDADE` e `PROGRESSIVA` no motor, com faixas persistidas em JSONB na regra |
| RF-VR-10 | Modificadores e mínimo por linha | 🚧 | Multiplicador, acréscimo unitário, acréscimo fixo e mínimo persistidos na regra; falta tela de cadastro |
| RF-VR-11 | `ROUND_HALF_UP`, unitário 4 casas, soma das linhas | 🚧 | Motor usa unitário 4 casas, `ROUND_HALF_UP` e `ratear_desconto` com resíduo na última linha; persistência e documentos seguem com 2 casas |
| RF-VR-12 | Vigência de regras; regra usada nunca editada | 🚧 | `POST /regras/{id}/suceder` encerra a atual e cria nova com vigência; o legado (reajuste em bloco) ainda edita `preco_venda` in loco |
| RF-VR-13 | Preço manual e limite de desconto por perfil | 🚧 | Campos editáveis no PDV, mas sem permissão `preco.manual`, justificativa, limite ou aprovação. RBAC existe só para preço de cadastro |
| RF-VR-14 | Explicação do preço na linha | 🚧 | `explicacao` devolvida em venda/OS na resposta que calculou; é transiente e não sobrevive a um GET (só item terceirizado tem `snapshot_preco` gravado) |
| RF-VR-15 | Reprecificação em lote com simulação | 🚧 | Simular/aplicar/histórico existem, mas editam `preco_venda` sem vigência nem regras novas |
| RF-VR-16 | Ficha de consumo e custo de processo | 🚧 | `ficha_consumo` com vigência, insumo (produto com estoque), `quantidade_por_unidade`, `perda_percentual` e `custo_processo_unitario`; sem tabela separada de insumo/custo de processo |
| RF-VR-17 | Custo, margem e alertas por variação | 🚧 | Cálculo determinístico de custo e margem, gravado no snapshot de venda/OS; alerta só para insumo sem custo |
| RF-VR-18 | Estoque na variação vs no insumo | 🚧 | Insumo reaproveita `produto`/`produto_estoque`; filha acabada mantém saldo próprio; serviço ainda não gera variação |
| RF-VR-19 | Baixa atômica | 🚧 | Baixa atômica de produto no PDV **e de insumo na OS** (`UPDATE ... WHERE saldo >= qtd`, 409 + kardex); sem conversão de unidades |
| RF-VR-20 | Consumo previsto, reserva e baixa real | 🚧 | Previsto congelado ao entrar em produção e real baixado por endpoint idempotente; coluna `reservado` continua sem uso |
| RF-VR-21 | Snapshot completo em orçamento/OS | 🚧 | `regra_aplicada` JSONB com origem, regra, vigência, explicação, custo e margem; ainda sem variação/opções/dados fiscais |
| RF-VR-22 | `versao` e 409 em itens/regras/documentos | ⬜ | 409 existe para estoque/integridade; sem coluna `versao` em produto, OS ou venda |
| RF-VR-23 | Quantidade final visível (cópias × páginas) | ⬜ | Só campo livre `dimensoes` |
| RF-VR-24 | Catálogo mestre da matriz → filiais | 🚧 | Outbox com uuid idempotente e evento `mestre:produto`; a descida casa por `codigo`, não por uuid, e cada filial gera suas variantes localmente |
| RF-VR-25 | Modo leitura da licença (423) | ✅ | Middleware global bloqueia escrita com 423 e mantém GET livre |
| RF-VR-26 | Gating por módulo | 🚧 | Middleware e 403 existem, mas com os módulos do PRD v3.0 e desligado por padrão (`PRINTGEST_GATING_MODULOS=false`) |
| RF-VR-27 | Assistente de agrupamento e importação de planilha | ⬜ | Sem CSV/XLSX; desktop mostra apenas "disponível na próxima etapa" |
| RF-VR-28 | Relatórios por variação | ⬜ | Só faturamento por filial e aniversariantes |

**Fases:** V0 em andamento · V1 em andamento (falta a UI de cadastro) · V2 em andamento (fichas, custo/margem, previsto e baixa real; falta conversão de unidades e reserva) · V3 proposta · V4 proposta.

---

## 1. Objetivo, público e premissas

**Objetivo.** Orientar a equipe de desenvolvimento e de produto a modelar e construir o fluxo de **produtos e serviços com variações**: o mesmo item vendido com preço, custo, consumo de estoque e produção diferentes conforme material, tamanho, cor, acabamento e quantidade.

**Público:** desenvolvimento, produto, design e quem vai cadastrar o catálogo na gráfica.

**Exemplo-guia do negócio (impressão):**

| Variação (substrato) | Preço informado |
| --- | --- |
| Sulfite | R$ 1,00 |
| Papel alta alvura | R$ 8,00 |
| Papel fotográfico | R$ 10,00 |

### 1.1 Premissas assumidas (confirmar)

O exemplo não diz a que o preço se refere. Para escrever este guia, assumi o seguinte, e cada item está marcado para confirmação na seção 18.

| Id | Premissa | Se for diferente |
| --- | --- | --- |
| A-01 | A unidade de venda é **uma impressão**, isto é, uma face de uma folha de tamanho padrão (por exemplo A4) | Se for por folha frente e verso, por centímetro quadrado ou por página, muda a unidade e o cálculo (seção 7.6) |
| A-02 | O preço inclui o papel (o substrato faz parte do preço) | Se o papel for cobrado à parte, o substrato vira insumo e o preço vira serviço de impressão |
| A-03 | O preço é o mesmo para qualquer cobertura de tinta e para cor ou preto e branco | Se variar, cor e cobertura entram como eixos ou modificadores (seções 4 e 7) |
| A-04 | O PrintGest já tem cadastro de produtos e serviços, orçamento, OS, venda de balcão, estoque e custo real (escopo do PRD v3.0, **não analisado** para este guia) | O modelo de dados da seção 6 precisa ser conciliado com as tabelas existentes |

### 1.2 Regras de plataforma que este guia respeita

- Dinheiro e quantidade em `NUMERIC`/`Decimal`, nunca `float`, com `ROUND_HALF_UP` explícito.
- Toda entidade sincronizável tem `uuid` e `filial_id`; entidades editáveis têm `versao`, com `409` em conflito (orçamento e OS).
- **Cadastros mestres** (produto, tabela de preços, parâmetros) nascem na matriz e descem para as filiais (RF-FL-03).
- Parâmetros de precificação têm **data de vigência** e não alteram orçamentos já emitidos, que guardam um **snapshot** (RF-SY-06).
- Gating por módulo no servidor (`OS_ORCAMENTO`, `VENDA_BALCAO`, `COMPRAS_ESTOQUE`) e **modo leitura** sem escrita quando a licença não estiver válida.

---

## 2. O problema em termos de negócio

O mesmo serviço aparece em várias formas. Sem um modelo de variações, a gráfica cai em um destes caminhos ruins:

| Caminho | Sintoma |
| --- | --- |
| Um cadastro por combinação («Impressão sulfite A4», «Impressão sulfite A3», «Impressão alta alvura A4»...) | Catálogo com centenas de itens parecidos; erro de digitação; relatórios que não somam «impressões» |
| Um cadastro único com preço digitado na hora | Preço diferente para o mesmo caso; margem desconhecida; consumo de estoque impossível de calcular |
| Planilha paralela de preços | Preço desatualizado; ninguém sabe qual é o vigente |

**O que o fluxo precisa entregar:** escolher o item, escolher as opções, informar a quantidade e obter **preço, custo, margem, consumo de insumos e ficha de produção** de forma automática, explicável e consistente entre balcão, orçamento e OS.

---

## 3. Conceitos

| Termo | Definição | Exemplo |
| --- | --- | --- |
| Item de catálogo | Algo que a gráfica vende. Pode ser **produto** (revenda, com estoque próprio) ou **serviço** (produção, que consome insumos) | Impressão (serviço); Caneta (produto) |
| Eixo de variação | Uma característica que muda o item | Substrato, tamanho, cor, lados, acabamento |
| Opção | Um valor possível de um eixo | Sulfite, alta alvura, fotográfico |
| Variação | Uma combinação completa de opções de um item | Impressão, fotográfico, A4, colorida |
| SKU | Código único de uma variação | `IMP-FOTO-A4-COR` |
| Modificador | Um ajuste de preço ou de consumo por uma opção opcional | Laminação fosca: acréscimo por unidade |
| Regra de preço | Define o preço de uma variação, de um modificador ou de uma faixa de quantidade, com vigência e prioridade | Sulfite de 50 a 199 unidades: R$ 0,80 |
| Faixa de quantidade | Intervalo de quantidade com preço unitário próprio | 1 a 49, 50 a 199, 200 ou mais |
| Ficha de consumo | Lista de insumos e quantidades gastas por unidade vendida de uma variação | 1 folha A4 de sulfite por impressão |
| Snapshot | Cópia congelada dos valores usados em um orçamento ou OS | Preço unitário, regra aplicada, custo e opções no momento da emissão |

---

## 4. Tipos de variação em uma gráfica

Cada eixo afeta de maneira diferente o preço, o custo, o estoque, a produção e o fiscal. Essa tabela decide **como** cada tipo deve ser modelado.

| Eixo | Exemplos | Preço | Custo | Estoque | Produção | Como modelar |
| --- | --- | --- | --- | --- | --- | --- |
| Substrato (material) | Sulfite, alta alvura, fotográfico, couchê, adesivo | **Define o preço base** | Muda | **Muda o insumo consumido** | Muda a bandeja e a máquina | Eixo obrigatório que gera variações |
| Tamanho | A5, A4, A3, 10x15, 13x18 | Muda | Muda | Muda (corte e aproveitamento) | Muda o formato de saída | Eixo obrigatório, ou fórmula por área quando houver tamanho livre |
| Cor | P&B, colorido | Costuma mudar | Muda (toner ou tinta) | Muda (consumo de toner) | Muda a máquina | Eixo obrigatório ou opcional com valor padrão |
| Lados | Frente, frente e verso | Costuma multiplicar | Dobra a impressão | Idem | Muda o fluxo da máquina | Modificador multiplicador |
| Gramatura | 75 g, 90 g, 120 g, 180 g | Muda | Muda | Muda o insumo | Muda a regulagem | Parte do substrato (uma opção por papel e gramatura) |
| Acabamento | Laminação, corte, dobra, espiral, furo | Soma | Soma | Pode consumir insumo | Etapa extra | Modificador opcional (acréscimo fixo ou por unidade) |
| Quantidade | 1 a 49, 50 a 199, 200 ou mais | Muda o preço unitário | Pode mudar (ganho de escala) | Proporcional | Lote | **Faixa de quantidade**, não eixo |
| Prazo ou urgência | Normal, urgente | Acréscimo | Pode mudar | Nenhum | Prioridade na fila | Modificador de pedido (não de item) |
| Cliente ou contrato | Tabela de preço do cliente | Muda | Não muda | Não muda | Não muda | Tabela de preço por cliente (seção 7.2) |
| Filial | Matriz, filial A | Pode mudar | Pode mudar | Por filial | Por filial | Regra com `filial_id` (seção 11.8) |

**Regra de ouro:** o que muda o **insumo consumido** ou o **preço base** deve ser eixo que gera variação (substrato, tamanho, cor). O que apenas **soma ou multiplica** um valor sobre o preço base deve ser modificador (acabamento, lados, urgência). Quantidade é sempre faixa.

---

## 5. Como modelar: opções e recomendação

| Opção | Descrição | Prós | Contras |
| --- | --- | --- | --- |
| **A. Um item por combinação** | Cada variação é um cadastro independente | Simples de implementar; preço e estoque diretos | Explosão combinatória; manutenção pesada; relatórios dispersos |
| **B. Item base com eixos e variações geradas** | Um item, N eixos, uma variação por combinação | Catálogo organizado; relatórios por item e por variação | Ainda gera muitas variações se houver muitos eixos |
| **C. Item base com modificadores** | Um preço base e acréscimos por opção | Poucos cadastros; ótimo para opcionais | Não separa consumo de insumo por substrato; preço fica opaco |
| **D. Híbrido (recomendado)** | Eixos obrigatórios que **geram variações** (substrato, tamanho, cor), mais **modificadores** para opcionais (lados, acabamento, urgência) e **faixas de quantidade** | Equilíbrio: preço e consumo corretos onde importam; cadastro enxuto onde não importa | Exige regras de precedência claras (seção 7) |

### 5.1 Por que o híbrido

1. O exemplo do negócio mostra que o substrato muda **muito** o preço (R$ 1,00, R$ 8,00, R$ 10,00) e também o insumo gasto. Isso pede variação de verdade (opção B).
2. Acabamentos e lados somam ou multiplicam sobre qualquer substrato. Se cada um gerasse variações, o número explodiria (opção C evita isso).
3. Quantidade é uma regra de preço, não um atributo do item.

### 5.2 O limite da explosão

Cinco tamanhos, dois modos de cor, três substratos e dois lados geram 5 × 2 × 3 × 2 = **60** variações de um único serviço. Por isso:

- **Lados** fica como modificador multiplicador, o que reduz para 30.
- O sistema **avisa** quando os eixos obrigatórios gerarem mais de \[100\] variações e pede confirmação.
- As variações são criadas em **matriz editável**, com preenchimento em massa (seção 12).
- Combinações que não existem na gráfica são **desativadas** (seção 10).

### 5.3 Quando fugir do padrão

| Situação | Tratamento |
| --- | --- |
| Produto de revenda com estoque próprio por cor e tamanho (caneta, caderno, camiseta) | Variação com **estoque no nível da variação** (seção 9.1) |
| Preço por área (banner, adesivo em metro quadrado) | Serviço com **unidade de venda em m²** e tamanho livre (seção 7.6) |
| Pedido totalmente sob encomenda, sem tabela | Item «personalizado» com preço digitado, **com justificativa e aprovação** (seção 7.7) |

---

## 6. Modelo de dados proposto

Proposta de referência. Ela precisa ser conciliada com as tabelas já existentes do PRD v3.0 (premissa A-04). Todas as tabelas levam `uuid`, `filial_id` (quando operacionais), `criado_em`, `atualizado_em`, e `versao` nas editáveis.

### 6.1 Catálogo e variações

| Tabela | Campos principais | Observações |
| --- | --- | --- |
| `item_catalogo` | `id`, `uuid`, `tipo` (PRODUTO ou SERVICO), `nome`, `unidade_venda`, `usa_variacoes` (bool), `controla_estoque_na_variacao` (bool), `ativo`, `versao` | Mestre da matriz. `unidade_venda` é UN, M2, ML, FOLHA etc. |
| `eixo_variacao` | `id`, `item_id`, `codigo`, `nome`, `tipo` (SELECAO ou NUMERICO), `obrigatorio`, `gera_variacao` (bool), `ordem` | `gera_variacao = false` indica modificador (não gera SKU) |
| `opcao_variacao` | `id`, `eixo_id`, `codigo`, `rotulo`, `ordem`, `ativo` | Valor de um eixo |
| `variacao` | `id`, `uuid`, `item_id`, `sku`, `chave_canonica`, `ativo`, `versao` | **Único** (`item_id`, `chave_canonica`). A chave é a lista ordenada de ids de opções |
| `variacao_opcao` | `variacao_id`, `opcao_id` | Liga a variação às opções que a compõem |
| `compatibilidade` | `id`, `item_id`, `opcao_a_id`, `opcao_b_id`, `regra` (PROIBIDO ou EXIGE) | Combinações inválidas (seção 10) |

### 6.2 Preço

| Tabela | Campos principais | Observações |
| --- | --- | --- |
| `tabela_preco` | `id`, `uuid`, `nome`, `padrao` (bool), `cliente_id` (nulo), `filial_id` (nulo) | Uma tabela padrão; tabelas por cliente ou por filial são opcionais |
| `regra_preco` | `id`, `uuid`, `tabela_preco_id`, `item_id`, `variacao_id` (nulo), `opcao_id` (nulo, para modificador), `tipo` (UNITARIO, ACRESCIMO\_UNITARIO, ACRESCIMO\_FIXO, MULTIPLICADOR, MINIMO), `valor` NUMERIC(14,4), `qtd_min`, `qtd_max` (nulo = sem teto), `vigencia_inicio`, `vigencia_fim` (nulo), `prioridade`, `versao` | Uma regra por caso. Não pode haver sobreposição de faixa na mesma chave e vigência |

### 6.3 Custo e consumo

| Tabela | Campos principais | Observações |
| --- | --- | --- |
| `insumo` | `id`, `uuid`, `nome`, `unidade_estoque`, `custo_medio` NUMERIC(14,4), `estoque` NUMERIC(14,3) | Papel, toner, tinta, laminado, espiral |
| `ficha_consumo` | `id`, `variacao_id` (ou `opcao_id` do modificador), `insumo_id`, `quantidade_por_unidade` NUMERIC(14,4), `perda_percentual` NUMERIC(6,3), `vigencia_inicio`, `vigencia_fim` | Receita de uma unidade vendida. Conversões (resma e folha) pelo cadastro do insumo |
| `custo_processo` | `id`, `variacao_id` ou `opcao_id`, `descricao`, `valor_unitario`, `vigencia_inicio`, `vigencia_fim` | Máquina, mão de obra, toner por cobertura |

### 6.4 Documentos (snapshot)

| Tabela | Campos principais | Observações |
| --- | --- | --- |
| `documento_item` (orçamento, OS, venda) | `id`, `uuid`, `documento_id`, `item_id`, `variacao_id`, `opcoes_snapshot` (JSON), `quantidade`, `preco_unitario`, `custo_unitario`, `regras_aplicadas` (JSON), `desconto`, `total`, `versao` | **Congela** a explicação do preço: quais regras, em que vigência, com que valores |
| `consumo_previsto` e `consumo_real` | `documento_item_id`, `insumo_id`, `quantidade` | Previsto na aprovação e real na produção (custo real do v3.0) |

### 6.5 Regras de integridade

1. Não existem duas variações do mesmo item com a mesma `chave_canonica`.
2. Toda variação ativa de serviço tem ao menos uma regra de preço vigente e uma ficha de consumo, ou uma justificativa de que não consome insumo.
3. Faixas de quantidade de uma mesma chave e vigência não podem se sobrepor nem deixar buracos a partir de `qtd_min = 1`.
4. Variações com histórico (usadas em documentos) nunca são excluídas, apenas desativadas.
5. Preços e quantidades usam `NUMERIC`; o arredondamento do total da linha é `ROUND_HALF_UP` em 2 casas.
6. A edição de variação ou regra usa `versao`, com `409` em conflito.

---

## 7. Regras de preço

### 7.1 Como o preço é calculado

O cálculo é **determinístico** e roda no servidor (Local API Service), com o mesmo resultado no balcão, no orçamento e na OS.

```
funcao calcular_linha(item, opcoes, quantidade, cliente, filial, data):
  1. variacao = resolver_variacao(item, opcoes que geram variação)       # chave_canonica
  2. validar_compatibilidade(variacao, opcoes)                            # se inválida: erro COMBINACAO_INVALIDA
  3. tabelas = [tabela do cliente, tabela da filial, tabela padrão]        # na ordem
  4. regra = primeira regra UNITARIO vigente na data, da variação,
             cuja faixa contém a quantidade                              # se nenhuma: erro PRECO_NAO_CADASTRADO
  5. unitario = regra.valor
  6. unitario = unitario x produto dos MULTIPLICADORES das opções escolhidas
  7. unitario = unitario + soma dos ACRESCIMO_UNITARIO das opções escolhidas
  8. total = quantidade x unitario + soma dos ACRESCIMO_FIXO
  9. total = maximo(total, MINIMO da linha, se houver)
 10. total = arredondar_meio_para_cima(total, 2 casas)
 11. gravar snapshot: variação, opções, regra e tabela usadas, faixa, modificadores, valores
```

O sistema **nunca** devolve preço zero em silêncio: sem regra vigente, a emissão é bloqueada (ver 7.7 para preço manual).

### 7.2 Precedência das regras

| Ordem | Regra | Quando vale |
| --- | --- | --- |
| 1 | Regra específica da variação para o **cliente** | Contrato ou acordo especial |
| 2 | Tabela do cliente, por item | Cliente com tabela própria |
| 3 | Tabela da **filial** | Filial com preço próprio |
| 4 | Tabela **padrão** da variação | Caso geral |
| 5 | Nenhuma regra | **Erro** `PRECO_NAO_CADASTRADO`; só segue com preço manual aprovado (7.7) |

No mesmo nível, vale a regra de maior `prioridade`; em empate, a de vigência mais recente. O cadastro **impede** regras ambíguas (mesma chave, faixa e vigência sobrepostas).

### 7.3 Faixas de quantidade

Exemplo ilustrativo de faixas para o sulfite: de 1 a 49, R$ 1,00; de 50 a 199, R$ 0,80; a partir de 200, R$ 0,60. Há dois jeitos de aplicar a faixa:

| Modo | Como calcula | 120 impressões em sulfite |
| --- | --- | --- |
| **A faixa vale para toda a quantidade** (recomendado) | Acha a faixa da quantidade total e aplica o preço a todas as unidades | 120 × R$ 0,80 = **R$ 96,00** |
| Faixa progressiva | Cada unidade paga o preço da faixa em que cai | 49 × R$ 1,00 + 71 × R$ 0,80 = **R$ 105,80** |

O modo é configurável por item (`modo_faixa`: `TODA_A_QUANTIDADE` ou `PROGRESSIVA`). O primeiro é o mais comum em gráficas e o mais fácil de explicar, mas cria um efeito conhecido: 49 impressões custam R$ 49,00 e 50 custam R$ 40,00. O balcão deve **avisar** («a partir de 50 unidades o preço cai para R$ 0,80») em vez de esconder isso (decisão D-V1).

### 7.4 Modificadores

| Tipo | Efeito | Exemplo ilustrativo |
| --- | --- | --- |
| Multiplicador | Multiplica o preço unitário | Frente e verso: × 1,6 |
| Acréscimo por unidade | Soma ao preço unitário | Laminação fosca: + R$ 2,00 por impressão |
| Acréscimo fixo | Soma ao total da linha, uma vez | Taxa de arte ou de setup: + R$ 30,00 |
| Mínimo por linha | Piso do total da linha | Mínimo de R$ 5,00 |

**Ordem de aplicação:** multiplicadores, depois acréscimos por unidade, depois acréscimos fixos, depois o mínimo. Essa ordem precisa estar escrita na tela de cadastro, porque muda o resultado.

**Exemplos calculados** (preços base do negócio; modificadores e faixas ilustrativos):

| Pedido | Cálculo | Total da linha |
| --- | --- | --- |
| 1 impressão em sulfite | 1 × 1,00 = 1,00; o mínimo de R$ 5,00 se aplica | **R$ 5,00** |
| 10 impressões em alta alvura | 10 × 8,00 | **R$ 80,00** |
| 25 impressões em fotográfico com laminação fosca | 25 × (10,00 + 2,00) | **R$ 300,00** |
| 100 impressões em sulfite, frente e verso, com corte (+ R$ 0,10 por unidade) | Faixa de 50 a 199: 0,80 × 1,6 = 1,28; + 0,10 = 1,38; 100 × 1,38 | **R$ 138,00** |

### 7.5 Arredondamento e exibição

- O preço unitário é guardado com **4 casas**; o total da linha é arredondado com `ROUND_HALF_UP` em 2 casas.
- O total do documento é a **soma dos totais das linhas**, nunca o preço unitário arredondado multiplicado pela quantidade.
- A tela mostra o unitário com 2 casas e, se o arredondamento esconder diferença, mostra também as 4 casas (por exemplo, R$ 0,3333 × 300 = R$ 99,99).
- Desconto de documento rateado entre as linhas: a última linha absorve o resíduo de centavos.

### 7.6 Unidade de venda (premissa A-01)

| Unidade | Quando usar | Como a quantidade é obtida |
| --- | --- | --- |
| Impressão (uma face) | Padrão deste guia | Cópias × páginas × lados |
| Folha | Quando o preço é por folha, frente e verso incluído | Cópias × folhas |
| Metro quadrado | Banner, adesivo, lona, plotagem | Largura × altura em cm, convertida para m² com 3 casas, com **mínimo cobrável** configurável (decisão D-V6) |
| Metro linear | Bobina, fita | Comprimento informado |
| Unidade | Produto pronto (cartão, convite) | Quantidade informada |

O produto precisa **mostrar a quantidade final** usada no cálculo, para o atendente conferir («100 cópias × 3 páginas = 300 impressões»).

### 7.7 Preço manual e desconto

| Situação | Regra |
| --- | --- |
| Item personalizado sem tabela | Permissão `preco.manual`; justificativa obrigatória; aparece no documento como «preço manual» |
| Desconto | Limite por perfil (por exemplo, atendente até \[**\]%, gerente até \[**\]%); acima do limite exige aprovação |
| Preço abaixo do custo ou da margem mínima | Alerta forte e aprovação do gerente; bloqueio configurável |
| Auditoria | Quem alterou, quando, valor anterior, justificativa e regra original |

### 7.8 Vigência e alteração de preços

1. Uma alteração de preço **cria uma regra nova** com vigência inicial; a regra anterior recebe `vigencia_fim` no dia anterior. A regra usada em documento nunca é editada.
2. Antes de publicar, o sistema mostra uma **simulação de impacto** (preço antigo e novo, variação percentual, margem).
3. Reprecificação em **lote** por filtro (item, eixo, percentual ou valor), sempre com simulação e confirmação.
4. Documentos emitidos **não mudam** (snapshot). Orçamentos em aberto mantêm o preço até a validade; vencidos são recalculados (decisão D-V3).
5. Alterações viram eventos para a sincronização com as filiais (a matriz publica; as filiais recebem).

### 7.9 Explicação do preço

Cada linha tem um detalhamento clicável: variação escolhida, tabela aplicada, faixa, preço base, modificadores com seus valores, mínimo, desconto, total e origem («tabela padrão», «tabela do cliente», «manual»). É o que resolve discussões de balcão e dá confiança ao atendente.

---

## 8. Custo e margem

### 8.1 Fórmula

- **Custo unitário** = Σ (consumo do insumo × custo do insumo × (1 + perda)) + Σ custos de processo + custos dos modificadores escolhidos.
- **Margem bruta** = (preço unitário − custo unitário) ÷ preço unitário.

### 8.2 Exemplo ilustrativo (custos fictícios)

| Variação | Preço | Papel | Toner ou tinta | Processo | Custo | Margem bruta |
| --- | --- | --- | --- | --- | --- | --- |
| Impressão em sulfite | R$ 1,00 | 0,05 | 0,12 | 0,08 | 0,25 | 75,0% |
| Impressão em alta alvura | R$ 8,00 | 2,00 | 0,15 | 0,10 | 2,25 | 71,9% |
| Impressão em fotográfico | R$ 10,00 | 3,50 | 1,20 | 0,30 | 5,00 | 50,0% |

O exemplo mostra por que o substrato precisa ser variação: o **custo** e a **margem** mudam bastante, e uma margem única para «Impressão» esconderia que o fotográfico rende menos.

### 8.3 Fonte do custo

| Item | Regra proposta |
| --- | --- |
| Custo do insumo | Custo médio ponderado, atualizado a cada entrada de compra (decisão D-V4) |
| Custo de processo | Cadastro com vigência (máquina, mão de obra) |
| Custo no documento | **Snapshot** na emissão, para auditar a margem prevista |
| Custo real | Apurado depois da produção, com o consumo real (escopo do v3.0) |

### 8.3.1 Alertas de margem

- Variação com preço abaixo do custo ou da margem mínima do item.
- Variação sem ficha de consumo ou sem custo vigente.
- Custo do insumo sem atualização há mais de \[\_\_\] dias.
- Variação sem regra de preço vigente.

### 8.4 Serviço terceirizado

Quando uma variação é executada por fornecedor (por exemplo, encadernação externa), o custo vem da **cotação do fornecedor** e não da ficha de consumo. Isso depende do fluxo de orçamento com fornecedor do v3.0, que não foi analisado; a modelagem precisa de um campo de origem de execução (`INTERNA` ou `EXTERNA`) na variação.

---

## 9. Estoque e consumo

### 9.1 Dois modelos de estoque

| Tipo de item | Onde fica o estoque | Exemplo | Movimento |
| --- | --- | --- | --- |
| **Produto de revenda** | **Na variação** (um saldo por SKU) | Caneta azul e caneta preta; camiseta M e G | Venda baixa o saldo da variação |
| **Serviço de produção** | **No insumo**; a variação aponta para insumos pela ficha de consumo | Impressão em fotográfico consome papel fotográfico e tinta | Produção baixa os insumos |

O campo `controla_estoque_na_variacao` do item decide qual dos dois vale. Um item nunca usa os dois.

### 9.2 Momentos do consumo

| Momento | O que acontece | Configurável |
| --- | --- | --- |
| Orçamento | Calcula o **consumo previsto** e mostra a disponibilidade de insumos | Sim |
| Aprovação da OS | **Reserva** os insumos (opcional) | Sim |
| Início ou conclusão da produção | **Baixa** o consumo real | Sim |
| Perda | Registra perda real (diferente da prevista) com motivo | Sim |

A baixa é **atômica** (`UPDATE ... WHERE saldo >= quantidade`, como no restante da plataforma). Sem saldo, o orçamento avisa e a produção só avança com permissão e justificativa.

### 9.3 Unidades e conversões

| Insumo | Unidade de compra | Unidade de uso | Fator |
| --- | --- | --- | --- |
| Papel sulfite | Resma | Folha | 500 |
| Papel fotográfico | Pacote | Folha | \[\_\_\] |
| Bobina de adesivo | Metro linear | m² | Largura da bobina |
| Toner e tinta | Cartucho | Impressão estimada | Rendimento do fabricante |

As conversões ficam no cadastro do insumo, e a ficha de consumo usa a unidade de uso.

### 9.4 Toner e tinta

- **Início (recomendado):** custo fixo por impressão, dentro do custo de processo (8.2).
- **Depois:** consumo por cobertura estimada (percentual de cobertura × rendimento do cartucho). Só vale a pena quando o custo de tinta varia muito entre pedidos.

### 9.5 Aproveitamento e perda

- **Rendimento do corte:** se uma folha A3 rende 2 impressões A4, a ficha usa `quantidade_por_unidade = 0,5` folha A3 por impressão A4.
- **Perda percentual** por variação (acertos de máquina, papel danificado), somada ao consumo previsto.
- Diferença entre previsto e real alimenta o custo real e a revisão da ficha.

### 9.6 Compras

A reposição trabalha **por insumo**, com ponto de pedido e sugestão baseada no consumo previsto das OS abertas. Variações de produtos de revenda repõem por SKU.

---

## 10. Compatibilidade e restrições

### 10.1 Tipos de restrição

| Tipo | Significado | Exemplo ilustrativo |
| --- | --- | --- |
| Proibida | A combinação das opções A e B não pode ser vendida | Papel fotográfico não aceita frente e verso |
| Exige | A opção A só existe com a opção B | Laminação exige substrato compatível |
| Limite de quantidade | Mínimo e máximo por variação | Alta alvura de 120 g: mínimo de 10 unidades |
| Limite de tamanho | Máximo físico da máquina | Tamanho máximo de impressão por equipamento |
| Prazo mínimo | Dias para produzir a variação | Fotográfico: \[\_\_\] horas |
| Disponibilidade | Variação só em certas filiais | Plotagem só na matriz |

Os exemplos são ilustrativos; as regras reais vêm do chão de fábrica da gráfica.

### 10.2 Comportamento

1. O **servidor valida**; a tela apenas ajuda. Combinação inválida responde `422` com o código `COMBINACAO_INVALIDA` e a regra violada.
2. Opção incompatível aparece **desabilitada, com o motivo** («não disponível para papel fotográfico»).
3. Ao trocar um eixo, os eixos dependentes que ficaram inválidos voltam ao padrão, com aviso visível.
4. Variação **inativa** deixa de aparecer no balcão, mas permanece no histórico e nos documentos antigos. Documento em aberto com variação desativada pode ser emitido ou deve ser revisto, conforme a decisão D-V5.

---

## 11. Fluxos

### 11.1 Cadastro de um item com variações (assistente)

O item tem três estados: **rascunho** (editável, não aparece no balcão), **publicado** e **inativo**.

| Passo | O que o usuário faz | Validação |
| --- | --- | --- |
| 1. Dados básicos | Escolhe produto ou serviço, nome, unidade de venda e dados fiscais | Nome único; unidade obrigatória |
| 2. Eixos | Cria os eixos (substrato, tamanho, cor...) e marca se cada um **gera variação** ou é **modificador** | Ao menos um eixo que gera variação, se usa variações |
| 3. Opções | Cadastra as opções de cada eixo | Sem opções repetidas no mesmo eixo |
| 4. Gerar variações | O sistema cria a matriz de combinações; o usuário desativa as que não existem | Aviso quando passar de \[100\] variações |
| 5. Preço | Preenche o preço da tabela padrão por variação, as faixas de quantidade e os modificadores | Variação ativa sem preço bloqueia a publicação |
| 6. Consumo e custo | Preenche a ficha de consumo e o custo de processo por variação; pode copiar de outra variação | Serviço de produção sem ficha exige justificativa |
| 7. Revisão e publicação | Confere o resumo: variações sem preço, sem ficha, com margem baixa | Publica e o catálogo desce às filiais |

### 11.2 Orçamento e OS

1. O atendente escolhe o **item**.
2. Escolhe as opções dos **eixos obrigatórios** (substrato, tamanho, cor), nessa ordem.
3. Informa a **quantidade** (cópias × páginas, ou medidas, conforme a unidade).
4. Marca os **opcionais** (frente e verso, acabamentos).
5. Vê o **preço e a explicação** em tempo real.
6. Ajusta desconto ou preço manual, se tiver permissão.
7. Adiciona a linha ao documento.

**Quando o preço congela:** enquanto o orçamento está em edição, o preço **recalcula** com o catálogo vigente. Ao **emitir** o orçamento ou **aprovar** a OS, a linha recebe o **snapshot** e não muda mais. A edição de um documento já emitido usa `versao` e responde `409` em conflito.

### 11.3 Venda de balcão

- **Favoritos:** as variações mais vendidas ficam em atalhos de um toque; o resto se escolhe pelos eixos.
- Item **sem variações** não pergunta nada além da quantidade.
- Produtos de revenda são lidos por **código de barras do SKU**.
- O total aparece em destaque; a explicação do preço fica a um clique.
- Meta de desempenho: cálculo e atualização da tela em menos de 300 ms em LAN.

### 11.4 Produção

A ficha de produção mostra: item, **variação e opções**, quantidade, **consumo previsto** de cada insumo, acabamentos e observações do cliente. O operador registra **perdas** e conclui; a conclusão baixa o consumo real.

### 11.5 Estoque e compras

Ver a seção 9. Reposição por insumo, e por SKU nos produtos de revenda.

### 11.6 Alteração e inativação

| Ação | Regra |
| --- | --- |
| Alterar preço | Cria regra nova com vigência (7.8); nunca edita a usada |
| Alterar ficha de consumo | Cria nova versão com vigência |
| Renomear opção | Permitido; documentos antigos preservam o rótulo do snapshot |
| Remover opção já usada | **Proibido**; só inativar |
| Adicionar opção a um eixo | Cria variações em rascunho, sem preço; bloqueia a publicação até preencher |
| Inativar variação | Some do balcão; mantém histórico |
| Mesclar variações duplicadas | Por assistente, com migração dos vínculos |

### 11.7 Migração do catálogo existente

Se a gráfica já tem itens como «Impressão sulfite» e «Impressão alta alvura», um **assistente de agrupamento** sugere unir itens de nome parecido em um item com eixo. Regras:

1. O usuário confirma cada agrupamento; nada é automático.
2. Os documentos antigos continuam apontando para o item antigo, que fica **inativo** com vínculo à variação nova (`variacao_origem`).
3. A importação por **planilha** (CSV ou XLSX) tem prévia, validação linha a linha e é **idempotente**.
4. A migração roda primeiro em cópia do banco de teste, com relatório de diferenças.

### 11.8 Filiais

| Tema | Regra |
| --- | --- |
| Dono do catálogo | A **matriz** (RF-FL-03): itens, eixos, opções, variações e a tabela de preço padrão descem às filiais |
| Preço por filial | Só com tabela da filial permitida (D-V2); senão, a filial usa a padrão |
| Disponibilidade | Variação pode ser limitada a algumas filiais (por exemplo, plotagem só na matriz) |
| Ordem de aplicação na sincronização | Item, eixos, opções, variações, regras de preço, fichas |
| Idempotência | Por `uuid` de cada entidade |
| Filial sem internet | Usa o último catálogo sincronizado e mostra a data da última atualização |
| Documentos da filial | Usam o snapshot do momento da emissão |

### 11.9 Modo leitura da licença

O catálogo continua **consultável** e um simulador de preço (sem salvar) pode ficar disponível. Criar ou alterar itens, variações, regras e documentos responde `423` (`LICENCA_RESTRITA`).

### 11.10 Gating por módulo (a confirmar com a matriz do v3.0)

| Função | Módulo sugerido |
| --- | --- |
| Catálogo, preço por variação, orçamento e OS | `OS_ORCAMENTO` |
| Venda de balcão com variações | `VENDA_BALCAO` |
| Ficha de consumo, baixa e reposição | `COMPRAS_ESTOQUE` |
| Relatórios por variação | `RELATORIOS` |

---

## 12. Experiência de uso

### 12.1 Princípios

1. **Rapidez no balcão:** poucos toques, valores padrão inteligentes.
2. **Preço visível enquanto se escolhe**, com a explicação a um clique.
3. **Nada escondido:** efeitos como a quebra por faixa são avisados.
4. **Erro com saída:** toda mensagem diz o que fazer.
5. **Cadastro em massa:** quem cadastra 60 variações não pode fazer isso uma a uma.

### 12.2 Cadastro: matriz editável

- Linhas são as variações; colunas são preço, faixas, custo, SKU e ativo.
- Preenchimento em massa: copiar de outra variação, aplicar percentual a um conjunto selecionado, preencher coluna.
- Células obrigatórias vazias ficam destacadas; o botão de publicar mostra a contagem de pendências.
- Filtro por eixo, contador de variações e aviso de explosão combinatória.
- Atalhos de teclado e desfazer.

### 12.3 Seleção no balcão e no orçamento

| Situação | Componente |
| --- | --- |
| Eixo com até 5 opções | Botões segmentados |
| Eixo com mais opções | Lista com busca |
| Opcionais (modificadores) | Caixas de seleção com o valor ao lado |
| Quantidade | Campo numérico, com soma de cópias × páginas visível |
| Preço | Total e unitário em destaque; botão «Ver como foi calculado» |

Ordem dos eixos: substrato, tamanho, cor, lados, acabamentos. Opções mais vendidas aparecem primeiro. O cliente recorrente pode usar «repetir o último pedido».

### 12.4 Estados de tela e mensagens

| Situação | Mensagem |
| --- | --- |
| Preço não cadastrado | Esta combinação não tem preço cadastrado. Peça ao gerente para cadastrar ou use preço manual. |
| Combinação inválida | Esta opção não está disponível com \[opção escolhida\]. |
| Sem estoque de insumo | Estoque de \[insumo\] insuficiente para esta quantidade. Disponível: \[n\]. |
| Variação inativa | Esta variação foi desativada e não pode mais ser vendida. |
| Modo leitura | Sistema em modo leitura: não é possível criar ou alterar registros. |
| Conflito de edição | Este registro foi alterado por outra pessoa. Recarregue para ver a versão atual. |
| Quebra de faixa | Compre \[n\] ou mais e o preço unitário cai para \[valor\]. |

### 12.5 Acessibilidade e desempenho percebido

- Contraste mínimo de 4,5:1, navegação completa por teclado, foco visível e rótulos em todos os campos.
- O preço atualizado é anunciado a leitores de tela (região `aria-live` educada).
- Estados nunca indicados só por cor.
- Cálculo no servidor em menos de 100 ms; cache do catálogo no desktop; espera de 150 ms após digitar a quantidade antes de recalcular.

---

## 13. Fiscal (cuidado: não é aconselhamento tributário)

- Os campos fiscais ficam no **item** e podem ser **sobrescritos na variação**: NCM, origem, CFOP padrão, CST ou CSOSN, código de serviço (lista da LC 116/2003) e descrição na nota.
- **Produto de revenda** e **serviço de impressão** podem ter tratamento fiscal diferente. O papel fotográfico vendido como mercadoria é diferente da impressão sob encomenda. O enquadramento depende do caso e do regime da gráfica e **deve ser definido com o contador** (D-V7).
- A descrição da linha na nota é **composta pelo item e pelas opções**, por modelo configurável (por exemplo, «Impressão em papel fotográfico A4»).
- O snapshot do documento guarda os dados fiscais usados, para auditoria.
- A emissão fiscal em modo leitura segue a decisão D-P4 do PRD do PrintGest.

---

## 14. Relatórios e análises

| Relatório | Pergunta que responde | Agrupamentos |
| --- | --- | --- |
| Vendas por variação | O que mais vende? | Item, variação, eixo, período, filial |
| Margem por variação | O que dá mais lucro? | Variação, cliente, período |
| Mix e curva ABC | Onde está a receita? | Item e variação |
| Consumo de insumos | Quanto papel e toner foram gastos? | Insumo, variação, período |
| Previsto contra real | Onde há perda ou ficha errada? | Variação, insumo |
| Descontos e preços manuais | Quem desconta mais e por quê? | Usuário, item, justificativa |
| Variações sem venda | O que pode ser desativado? | Variação, período |
| Efeito de reajuste | O que mudou depois da reprecificação? | Item, lote de reajuste |

---

## 15. Requisitos

### 15.1 Requisitos funcionais (RF-VR)

> O status de cada requisito no produto atual está no início deste documento,
> na seção **Status de implementação**.

**Catálogo**

- **RF-VR-01** O catálogo distingue **produto** (revenda) e **serviço** (produção), com unidade de venda.
- **RF-VR-02** Um item pode ter **eixos** e **opções**. Cada eixo é marcado como **gerador de variação** ou **modificador**.
- **RF-VR-03** O sistema gera as **variações** como combinações das opções dos eixos geradores, com `chave_canonica` única por item e SKU único.
- **RF-VR-04** O sistema avisa e pede confirmação quando as combinações geradas passarem do limite configurado (padrão 100).
- **RF-VR-05** Regras de **compatibilidade** (proibida, exige, limites, prazo, disponibilidade) são validadas **no servidor**, com `422` e o código `COMBINACAO_INVALIDA`.
- **RF-VR-06** O item tem estados **rascunho**, **publicado** e **inativo**; só o publicado aparece no balcão. A publicação é bloqueada se houver variação ativa sem preço (ou sem ficha de consumo, em serviço de produção, salvo justificativa).

**Preço**

- **RF-VR-07** O preço é calculado pelas etapas do 7.1, no servidor, com o mesmo resultado em balcão, orçamento e OS.
- **RF-VR-08** Precedência das regras: cliente, tabela do cliente, filial, padrão; sem regra vigente, erro `PRECO_NAO_CADASTRADO`, **nunca preço zero**.
- **RF-VR-09** **Faixas de quantidade** por variação, com modo configurável por item (toda a quantidade ou progressiva); sem sobreposição nem buracos.
- **RF-VR-10** **Modificadores** (multiplicador, acréscimo por unidade, acréscimo fixo) e **mínimo por linha**, na ordem definida no 7.4.
- **RF-VR-11** Arredondamento `ROUND_HALF_UP` em 2 casas no total da linha; unitário com 4 casas; total do documento é a soma das linhas.
- **RF-VR-12** Toda alteração de preço cria **regra nova com vigência**; a regra usada em documento nunca é editada.
- **RF-VR-13** **Preço manual** exige permissão e justificativa; **desconto** respeita o limite por perfil, com aprovação acima dele.
- **RF-VR-14** Cada linha tem a **explicação do preço** (7.9).
- **RF-VR-15** Reprecificação em **lote** com simulação de impacto e confirmação.

**Custo e estoque**

- **RF-VR-16** **Ficha de consumo** e **custo de processo** por variação e por modificador, com vigência.
- **RF-VR-17** Cálculo de **custo e margem** por variação e por linha, com alertas do 8.3.1.
- **RF-VR-18** Item de revenda controla estoque **na variação**; item de produção controla estoque **no insumo**. Nunca os dois.
- **RF-VR-19** **Baixa atômica** de insumo (`UPDATE ... WHERE saldo >= quantidade`), com perdas registráveis e conversões de unidade.
- **RF-VR-20** Consumo previsto no orçamento, reserva opcional na aprovação e baixa real na produção.

**Documentos**

- **RF-VR-21** Orçamento emitido e OS aprovada guardam **snapshot** de variação, opções, regras, custo, valores e dados fiscais.
- **RF-VR-22** Edição de documento usa `versao` e responde `409` em conflito.
- **RF-VR-23** A tela mostra a **quantidade final** usada no cálculo (cópias × páginas, ou área).

**Filiais, licença e migração**

- **RF-VR-24** O catálogo é **mestre da matriz** e desce às filiais, em ordem e de forma idempotente (11.8).
- **RF-VR-25** Em modo leitura da licença, o catálogo é consultável e as escritas respondem `423`.
- **RF-VR-26** As funções avançadas respeitam o gating por módulo (11.10).
- **RF-VR-27** Assistente de **agrupamento** e **importação por planilha**, com prévia, validação e idempotência.
- **RF-VR-28** Relatórios da seção 14.

### 15.2 Requisitos não funcionais

| Área | Requisito |
| --- | --- |
| Desempenho | Cálculo de preço no servidor com p95 abaixo de 100 ms; tela do balcão atualiza em menos de 300 ms em LAN |
| Escala | Meta de 5.000 variações por catálogo e 200 por item |
| Precisão | `NUMERIC` em dinheiro e quantidade; nunca `float` |
| Auditoria | Alterações de preço, de ficha, descontos e preços manuais com usuário, data, valor anterior e justificativa |
| Concorrência | `versao` e `409` em itens, regras e documentos |
| Resiliência | Filial sem internet opera com o último catálogo sincronizado |
| Acessibilidade | WCAG 2.1 AA; mensagens do 12.4 |
| Testabilidade | Cálculo de preço como função pura, coberta por tabela de casos (seção 16) |

---

## 16. Casos de teste

Usar os dados do **Anexo A**. Valores marcados como ilustrativos nas seções 7 e 8 servem de dados de teste.

| Id | Cenário | Resultado esperado |
| --- | --- | --- |
| T-VR-01 | Resolver a variação por opções em ordens diferentes | Mesma variação (a `chave_canonica` ignora a ordem) |
| T-VR-02 | Variação sem regra de preço vigente | `PRECO_NAO_CADASTRADO`; emissão bloqueada |
| T-VR-03 | Limites de faixa: 49, 50, 199 e 200 unidades | Faixas corretas nas bordas |
| T-VR-04 | 120 impressões em sulfite nos dois modos de faixa | R$ 96,00 (toda a quantidade) e R$ 105,80 (progressiva) |
| T-VR-05 | 100 sulfite, frente e verso, com corte | Unitário 1,38; total R$ 138,00 |
| T-VR-06 | 1 impressão em sulfite com mínimo de R$ 5,00 | Total R$ 5,00 |
| T-VR-07 | Arredondamento: R$ 0,3333 × 300; rateio de desconto | R$ 99,99; resíduo na última linha |
| T-VR-08 | Precedência: regra do cliente, filial e padrão | Vale a de maior precedência |
| T-VR-09 | Regra com vigência futura | A anterior termina no dia anterior; documentos antigos intactos |
| T-VR-10 | Alterar preço depois de emitir o orçamento | O orçamento emitido não muda |
| T-VR-11 | Combinação proibida | `422 COMBINACAO_INVALIDA` com a regra violada |
| T-VR-12 | Variação inativada | Some do balcão; permanece no histórico |
| T-VR-13 | Consumo previsto: 100 sulfite com 2% de perda | 102 folhas |
| T-VR-14 | Baixa de insumo sem saldo | Falha atômica; produção só segue com permissão |
| T-VR-15 | Rendimento de corte de 2 por folha | Consumo de 0,5 folha por unidade |
| T-VR-16 | Custo e margem do exemplo 8.2 | 75,0%, 71,9% e 50,0% |
| T-VR-17 | Desconto acima do limite do perfil | Exige aprovação |
| T-VR-18 | Preço manual sem permissão ou sem justificativa | Bloqueado |
| T-VR-19 | Edição simultânea de uma regra | `409` na segunda gravação |
| T-VR-20 | Sincronização para a filial | Ordem correta e idempotente por `uuid` |
| T-VR-21 | Filial sem internet | Usa o último catálogo e mostra a data |
| T-VR-22 | Modo leitura | Consulta e simulador funcionam; criar variação responde `423` |
| T-VR-23 | Ficha de consumo sem o módulo de estoque | `403 MODULO_NAO_LICENCIADO` |
| T-VR-24 | Agrupar itens antigos em um item com variações | Histórico preservado; itens antigos inativos com vínculo |
| T-VR-25 | Eixos que geram mais de 100 variações | Pede confirmação |
| T-VR-26 | Metro quadrado: 120 cm × 80 cm | 0,96 m², com o mínimo cobrável configurado |
| T-VR-27 | 100 cópias de documento com 3 páginas | Quantidade final de 300 impressões visível |

---

## 17. Plano de implementação em fases

> **Status atual:** V0, V1 e V2 em andamento — motor determinístico, regras com
> vigência e fichas de consumo já estão no código; V3 e V4 não iniciados (ver
> seção de status no início). A migration da V2 ainda precisa de autorização
> para ser aplicada em produção. As entregas abaixo permanecem como plano
> proposto.

| Fase | Entregas | Critério de pronto | Depende de |
| --- | --- | --- | --- |
| **V0 (mínimo útil)** | Item com eixos e variações; preço fixo por variação na tabela padrão; seleção no balcão e no orçamento; snapshot; explicação do preço; inativação | Vender os três substratos do exemplo com preço correto e histórico congelado | Cadastro de itens e orçamento do v3.0 |
| **V1** | Faixas de quantidade, modificadores, mínimo, compatibilidade, preço manual e descontos por perfil, matriz editável em massa | T-VR-01 a T-VR-12, T-VR-17 e T-VR-18 verdes | V0 |
| **V2** | Ficha de consumo, custo e margem, estoque, baixa, perdas, alertas | T-VR-13 a T-VR-16 e T-VR-23 verdes | Módulo de estoque; V1 |
| **V3** | Tabelas por cliente e por filial; sincronização completa; reprecificação em lote com simulação; importação e agrupamento do catálogo | T-VR-08, T-VR-19 a T-VR-21 e T-VR-24 verdes | Sync entre filiais (P5 do PrintGest) |
| **V4** | Relatórios, curva ABC, previsto contra real, serviço terceirizado | Aceite dos relatórios pelo cliente piloto | V2 |

**Primeira entrega recomendada:** V0 com o exemplo de impressão. É a menor parte que já resolve o problema relatado.

---

## 18. Decisões e perguntas em aberto

### 18.1 Decisões

| Id | Decisão | Recomendação |
| --- | --- | --- |
| D-V1 | Faixa de quantidade vale para toda a quantidade ou é progressiva | Toda a quantidade, com aviso de quebra no balcão; modo configurável por item |
| D-V2 | A filial pode ter tabela de preço própria? | Só quando a matriz permitir por item |
| D-V3 | Orçamento em aberto, depois de reajuste de preço | Mantém o preço até a validade; vencido é recalculado |
| D-V4 | Custo do insumo: médio ponderado ou último custo | Médio ponderado |
| D-V5 | Documento em aberto com variação inativada | Pode emitir uma vez, com aviso; novos itens não |
| D-V6 | Mínimo cobrável em metro quadrado e arredondamento da área | Definir com a gráfica (por exemplo, 0,5 m²) |
| D-V7 | Enquadramento fiscal de produto contra serviço por variação | Definir com o contador |
| D-V8 | Formato e modelo da planilha de importação | CSV com colunas por eixo, preço e faixas |
| D-V9 | Limite de variações por item | Alerta em 100; teto técnico em 200 |

### 18.2 Perguntas ao negócio (precisam de resposta para fechar o modelo)

1. **A que se refere o preço** (R$ 1,00, R$ 8,00 e R$ 10,00)? Uma face de uma folha A4? Uma folha frente e verso? Uma página?
2. O preço **inclui o papel** ou o papel é cobrado à parte?
3. O preço muda entre **colorido e preto e branco**? E por **cobertura de tinta**?
4. Quais **tamanhos** são vendidos, e algum é livre (por medida)?
5. Quais **acabamentos** existem e como são cobrados (por unidade, por pedido, por área)?
6. Existem **faixas de quantidade**? Onde elas começam e terminam, e valem para toda a quantidade ou para cada unidade?
7. Há **valor mínimo** por pedido ou taxa de arte e de setup?
8. Há **tabelas por cliente** ou contratos com preço especial? Quantos?
9. Algum item é **terceirizado** (encadernação, gráfica parceira)? Como o custo chega?
10. Quais produtos são de **revenda** com estoque próprio por cor e tamanho?
11. Quantos **itens ativos** o catálogo tem hoje e quantos têm nomes que repetem a mesma coisa («Impressão sulfite», «Impressão alta alvura»)?
12. A **filial** pode definir preço, ou só a matriz?
13. Quais combinações **não existem** na prática (para as regras de compatibilidade)?

---

## 19. Glossário

| Termo | Definição |
| --- | --- |
| Eixo gerador | Eixo cujas opções geram variações (substrato, tamanho, cor) |
| Modificador | Opção que soma ou multiplica sobre o preço base, sem gerar variação |
| Chave canônica | Lista ordenada dos ids de opções de uma variação; identifica a variação |
| Faixa de quantidade | Intervalo com preço unitário próprio |
| Ficha de consumo | Insumos e quantidades gastos por unidade vendida |
| Snapshot | Cópia congelada de preço, regras, custo e opções em um documento |
| Insumo | Material de produção em estoque (papel, toner, laminado) |
| Cliff | Efeito em que uma faixa maior torna o total menor que o de uma quantidade menor |

---

## Anexo A. Exemplo completo: serviço «Impressão»

Dados ilustrativos para desenvolvimento e teste, a partir do exemplo do negócio e das premissas A-01 a A-03.

### A.1 Item, eixos e opções

| Item | Tipo | Unidade | Eixo | Gera variação | Opções |
| --- | --- | --- | --- | --- | --- |
| Impressão | Serviço | Impressão (uma face de A4) | Substrato | Sim | Sulfite, Alta alvura, Fotográfico |
|  |  |  | Lados | Não (modificador) | Frente, Frente e verso |
|  |  |  | Acabamento | Não (modificador) | Nenhum, Corte, Laminação fosca |

### A.2 Variações geradas

| SKU | Variação | Preço base (tabela padrão) |
| --- | --- | --- |
| IMP-SULF | Impressão em sulfite | R$ 1,00 |
| IMP-ALVU | Impressão em papel alta alvura | R$ 8,00 |
| IMP-FOTO | Impressão em papel fotográfico | R$ 10,00 |

### A.3 Regras de preço ilustrativas

| Regra | Alvo | Valor |
| --- | --- | --- |
| Faixa 1 a 49 | IMP-SULF | R$ 1,00 |
| Faixa 50 a 199 | IMP-SULF | R$ 0,80 |
| Faixa 200 ou mais | IMP-SULF | R$ 0,60 |
| Multiplicador, frente e verso | Todas as variações | × 1,6 |
| Acréscimo por unidade, corte | Todas as variações | + R$ 0,10 |
| Acréscimo por unidade, laminação fosca | IMP-ALVU e IMP-FOTO | + R$ 2,00 |
| Acréscimo fixo, taxa de arte | Pedido | + R$ 30,00 |
| Mínimo por linha | Todas as variações | R$ 5,00 |

### A.4 Ficha de consumo e custo ilustrativos

| Variação | Insumo | Quantidade por impressão | Perda | Custo de processo |
| --- | --- | --- | --- | --- |
| IMP-SULF | Folha de sulfite A4 | 1 | 2% | R$ 0,20 (toner mais máquina) |
| IMP-ALVU | Folha de alta alvura A4 | 1 | 2% | R$ 0,25 |
| IMP-FOTO | Folha de fotográfico A4 | 1 | 3% | R$ 1,50 (tinta mais máquina) |

---

## Anexo B. Definição de pronto por fase

> Checklist ainda integralmente em aberto — nenhum item foi marcado como
> concluído; a seção de status no início registra o que o produto já cobre
> parcialmente.

- [ ] O cálculo de preço é uma função pura, no servidor, coberta pela tabela de casos da seção 16
- [ ] Dinheiro e quantidade em `NUMERIC`; `ROUND_HALF_UP` explícito
- [ ] Nenhum preço zero em silêncio: `PRECO_NAO_CADASTRADO` testado
- [ ] Snapshot gravado na emissão e na aprovação; alteração posterior de preço não afeta o documento
- [ ] Regras com vigência, sem sobreposição, e nunca editadas depois de usadas
- [ ] `versao` e `409` em itens, regras e documentos
- [ ] Compatibilidade validada no servidor (`422`), com mensagem na tela
- [ ] Catálogo desce às filiais em ordem, de forma idempotente, e a filial offline mostra a data da última atualização
- [ ] Modo leitura da licença e gating por módulo cobertos por teste
- [ ] Mensagens do 12.4 e acessibilidade verificadas
- [ ] Migração do catálogo existente testada em cópia, com relatório de diferenças
