# PRD v3.0 — PrintGest ERP

**Sistema de Gestão para Gráfica Rápida e Pequena Gráfica** · Versão 3.0.0 · 26 de outubro de 2026 · Status: rascunho para validação

**Baseline:** evolui os PRDs v2.2 (Python/FastAPI/PySide6) e v2.3 (C#/.NET 10). Preserva o que já existe (cadastros, PDV, OS, estoque, agendamento, Projetos/Kanban, financeiro, fiscal parcial, RBAC, licenciamento por plano) e **fecha as lacunas de cobertura** identificadas na análise: precificação, orçamento com fornecedor, custo real, estoque por consumo, arte e prova, produção por etapas, compras, financeiro e fiscal completos.

---

## 1. Visão Geral

### 1.1 Propósito

ERP desktop (Windows) em rede local, até 5 estações (10 no Enterprise), para gráficas rápidas e pequenas gráficas que **produzem parte dos serviços internamente e terceirizam outra parte com fornecedores**. O sistema cobre o ciclo completo: cadastro → orçamento → aprovação → arte → produção → entrega → cobrança → fiscal → custo real e margem.

### 1.2 Premissas mantidas do v2.2

- Local API Service obrigatório; estações-cliente nunca acessam o PostgreSQL.
- RBAC e gating de plano aplicados **no servidor**; o desktop só oculta menu.
- Licenciamento online-first via RedGest, com tolerância de 72 h e modo leitura.
- Valores monetários e quantidades sempre `Decimal`/`NUMERIC`, nunca `float`.
- LGPD proporcional (RBAC + backup); criptografia de PII segue em backlog.

### 1.3 O que muda nesta versão

| # | Mudança | Seção |
| --- | --- | --- |
| 1 | **Motor de precificação** configurável (substitui preço fixo por produto) | 3.1 |
| 2 | **Orçamento com fornecedor**: VF + 130% = CP; CP + 6% = valor do orçamento; só o total vai ao cliente | 3.2 |
| 3 | **Custo real por OS**, margem e orçado × realizado | 3.3 |
| 4 | **Estoque por consumo** (ficha técnica, unidade de compra × consumo, lote, sobras) | 3.4 |
| 5 | **Arte, prova e aprovação** por link | 3.5 |
| 6 | **Produção por etapas**, apontamento e rastreio de terceirizados | 3.6 |
| 7 | **Compras e cotação** | 3.7 |
| 8 | Financeiro completo (Pix/boleto, comissões, conciliação, DRE) | 3.8 |
| 9 | Fiscal completo (NFC-e, NF-e, NFS-e) | 3.9 |
| 10 | Reimpressão rápida, refação e pós-venda | 3.10 |
| 11 | **Matriz de planos corrigida** (caixa no Essencial; fiscal no Profissional) | 2 |

### 1.4 Fora de escopo (backlog)

Imposição/nesting automático de chapa, integração direta com RIP e máquinas, aplicativo móvel nativo, criptografia de PII com blind index, assinatura digital, réplica multi-servidor, compliance corporativo (SOX, ISO 9001, WCAG).

---

## 2. Planos e Módulos (matriz revisada)

Correções em relação ao v2.2/v2.3:

- **Caixa passa a existir no Essencial.** O PDV não pode operar sem abertura e fechamento de caixa.
- **“Contas a receber simples” no Essencial** (lançamento e baixa), porque a regra “OS entregue exige pagamento resolvido” depende dele. As demais funções financeiras ficam no Profissional.
- **Fiscal de emissão (NFC-e/NF-e/NFS-e) sobe para o Profissional.** Gráfica de balcão precisa emitir nota; exigir o plano de 10 estações para isso não faz sentido para o público-alvo.
- **Orçamento com fornecedor e motor de precificação entram no Essencial**, pois são o núcleo comercial de uma pequena gráfica.

| Módulo (id canônico) | Essencial (2 est.) | Profissional (5 est.) | Enterprise (10 est.) |
| --- | :-: | :-: | :-: |
| `cadastros` | ✅ | ✅ | ✅ |
| `movimento` (OS, orçamento, PDV, motor de preço, orçamento com fornecedor) | ✅ | ✅ | ✅ |
| `estoque` (saldo, kardex, reposição) | ✅ | ✅ | ✅ |
| `agendamento` | ✅ | ✅ | ✅ |
| `caixa` (abertura, sangria, fechamento) e contas a receber simples | ✅ | ✅ | ✅ |
| `configuracoes` | ✅ | ✅ | ✅ |
| `custos` (custo real, margem, orçado × realizado) | — | ✅ | ✅ |
| `estoque_avancado` (ficha técnica, lote, sobras) | — | ✅ | ✅ |
| `compras` (cotação, pedido de compra) | — | ✅ | ✅ |
| `arte` (versões, prova, aprovação por link) | — | ✅ | ✅ |
| `producao` (roteiro, apontamento, terceirizados) | — | ✅ | ✅ |
| `projetos` (Kanban) | — | ✅ | ✅ |
| `financeiro` (contas a pagar, plano de contas, Pix/boleto, comissões, conciliação, DRE) | — | ✅ | ✅ |
| `relatorios` | — | ✅ | ✅ |
| `fiscal` (emissão) | — | ✅ | ✅ |
| `multifilial` | — | — | ✅ |
| `api_integracao` | — | — | ✅ |

Regras: planos são aditivos; módulo não habilitado responde `403` no servidor e some do menu; `entitlements` ausente ou malformado não libera nenhum módulo extra. A dependência entre módulos deve ser validada na emissão do `entitlements` (ex.: não existe plano com `compras` sem `financeiro`).

---

## 3. Requisitos Funcionais

### 3.1 Motor de Precificação (`movimento`)

**Objetivo:** calcular o preço de produtos próprios a partir de variáveis, sem planilha externa.

- **Produto calculado**: além do produto de preço fixo, o catálogo aceita produto com **parâmetros** (formato, papel/gramatura, cores, acabamento, quantidade, prazo) e **fórmula** (preço por unidade, por m², por faixa).
- **Faixas de quantidade**: tabela por produto (ex.: 1–99, 100–499, 500+), com preço unitário ou total por faixa.
- **Tabela de preço por cliente**: desconto percentual ou preço específico por produto/categoria; precedência: preço do cliente > faixa > preço base.
- **Acréscimos**: urgência (prazo), arte, entrega, com valor ou percentual configurável.
- **Simulação**: o atendente altera variáveis e vê o preço recalculado na hora; o orçamento guarda o **snapshot** dos parâmetros usados.
- **Reajuste em bloco** (já existe) passa a atuar também sobre tabelas de faixa.
- **Piso de preço**: produto pode ter valor mínimo; abaixo dele, exige permissão de Gerente com justificativa.
- **Reaproveitamento**: “duplicar orçamento/OS” e “repetir pedido do cliente” copiam itens e parâmetros, recalculando pelos preços vigentes (exibe diferença para o valor anterior).

**Aceite:** mesmo conjunto de parâmetros produz sempre o mesmo preço; arredondamento centralizado; testes de paridade para faixas, desconto de cliente e m².

### 3.2 Orçamento com Fornecedor (serviço terceirizado)

Pequenas gráficas dependem de fornecedores para parte dos serviços (acabamento especial, grande formato, corte e vinco, hot stamping etc.). O orçamento precisa incorporar o valor do fornecedor sem expô-lo ao cliente.

#### 3.2.1 Regra de cálculo

| Sigla | Nome | Definição |
| --- | --- | --- |
| **VF** | Valor do fornecedor | Valor total cobrado pelo fornecedor pelo serviço cotado |
| **CP** | Custo de produção | `CP = VF + 130% de VF = VF × 2,30` |
| **VO** | Valor do orçamento | `VO = CP + 6% de CP = CP × 1,06` (≈ `VF × 2,438`; a fórmula normativa é a sequencial, com CP arredondado antes do VO) |

- Os dois percentuais são **acréscimos sobre a base anterior** (markup), não margem sobre o preço final. **Decidido com o responsável em 26/10/2026 (Q-01): confirmado** — "VF + 130% é custo; custo + 6% é markup". O parâmetro foi renomeado de `margem_orcamento_pct` para **`markup_orcamento_pct`** justamente para não reintroduzir a confusão.
- Os percentuais são **parâmetros** (Configurações > Precificação, somente Admin): `acrescimo_fornecedor_pct = 130` e `markup_orcamento_pct = 6`. A sobrescrita por fornecedor ou por categoria de serviço terceirizado é **opcional e planejada para o M2** (decisão Q-04, 26/10/2026).
- **Arredondamento** (modo único, meio para cima — `ROUND_HALF_UP` explícito, 2 casas; o padrão *banker's* do `Decimal` daria 200,90 no exemplo de VF 87,35): primeiro `CP` é arredondado; `VO` é calculado a partir do `CP` já arredondado. **A fórmula normativa é a sequencial** — o atalho `VF × 2,438` é aproximação e diverge em casos de borda (ex.: VF 0,05 → sequencial 0,13; direto 0,12).
- **Snapshot**: cada item terceirizado grava VF, os percentuais aplicados, CP e VO. Alterar o parâmetro global **não** altera orçamentos existentes; o recálculo é uma ação explícita, com registro em log.

**Exemplos**

| VF | CP (VF × 2,30) | VO (CP × 1,06) |
| --: | --: | --: |
| 100,00 | 230,00 | 243,80 |
| 87,35 | 200,91 | 212,96 |

#### 3.2.2 Fluxo do item terceirizado

1. No orçamento, o atendente adiciona um item do tipo **“Serviço de fornecedor”** (descrição, quantidade, especificação).
2. O item entra em **Aguardando cotação**. O orçamento fica em rascunho e **não pode ser enviado ao cliente**.
3. Quem tem permissão lança a cotação: fornecedor, VF, validade da cotação, prazo de entrega do fornecedor, observações e anexo (PDF/imagem da proposta).
4. O sistema calcula CP e VO e o item passa a **Cotado**.
5. Podem existir **várias cotações** para o mesmo item (fornecedores diferentes); uma é marcada como **selecionada** e só ela compõe o orçamento. Há um comparativo interno (VF, prazo, validade).
6. Cotação vencida gera aviso; o bloqueio de envio com cotação vencida é configurável.
7. Ao **aprovar** o orçamento e convertê-lo em OS, o sistema gera um **pedido de compra em rascunho** ao fornecedor selecionado, com o VF (ver 3.7) e cria a etapa “Terceirizado” no roteiro (ver 3.6).

**Ajuste manual:** Gerente/Admin pode sobrescrever o VO final com justificativa obrigatória. O sistema mostra a diferença em relação ao valor calculado e registra usuário, data e motivo.

#### 3.2.3 Confidencialidade (requisito crítico)

VF, CP, percentuais, nome do fornecedor e a composição do cálculo são **informação interna**. **Ao cliente é informado somente o valor total.**

- **Documento do cliente** (tela “visão do cliente”, PDF, impressão, mensagem por WhatsApp/e-mail, link de aprovação): exibe a descrição dos serviços e o **valor total do orçamento**. Não exibe VF, CP, percentuais, fornecedor, nem valor individual de itens terceirizados.
- **Geração no servidor, a partir de um modelo “seguro para cliente”.** O documento externo nunca é montado a partir do modelo interno com campos ocultos.
- **Permissões por campo** (novas):

| Permissão | Admin | Gerente | Operador | Caixa |
| --- | :-: | :-: | :-: | :-: |
| `ver_custo_terceiro` (VF, CP, percentuais, fornecedor) | ✅ | ✅ | — | — |
| `lancar_cotacao` (informar VF) | ✅ | ✅ | configurável | — |
| `ajustar_valor_orcamento` | ✅ | ✅ | — | — |
| `alterar_parametros_precificacao` | ✅ | — | — | — |

- Quem **lança** a cotação mas não tem `ver_custo_terceiro` informa o VF e passa a ver apenas o VO resultante; depois de salvo, o VF deixa de ser exibido a ele.
- A API **omite** os campos sensíveis (não os envia ocultos) para perfis sem permissão. Vale também para listagens, exportações, Kanban/cartão, OS de produção impressa, dashboards e relatórios.
- **Auditoria**: leitura de campos sensíveis por usuário autorizado não precisa de log; **alteração** de VF, percentuais ou VO sempre gera log append-only.

**Aceite:** teste automatizado percorrendo todas as rotas × todos os perfis garante que nenhuma resposta, PDF ou exportação para perfil sem permissão contém VF/CP/percentual/fornecedor.

### 3.3 Custo Real, Margem e Orçado × Realizado (`custos`)

- **Composição do custo da OS**: material consumido (3.4), serviços terceirizados (VF efetivamente pago), mão de obra e hora-máquina (taxas configuráveis, opcional) e perdas/refação.
- **Duas visões do custo de itens terceirizados**, mantidas separadas:
  - **Desembolso real** = valor efetivamente pago ao fornecedor (pode diferir do VF cotado; a diferença é registrada).
  - **CP gerencial** = VF × 2,30 (definição da seção 3.2), usado para formar preço e para análise gerencial.
- **Margem**: `valor faturado − custo`, em R$ e %, por OS, produto, cliente e vendedor. A margem sobre o desembolso real e a margem sobre o CP são exibidas separadamente.
- **Orçado × realizado**: compara valor e custo previstos no orçamento com o apurado na OS; desvios acima de limite configurável geram alerta ao Gerente.
- Visível apenas a perfis com `ver_custo_terceiro`.

### 3.4 Estoque por Consumo (`estoque_avancado`)

- **Unidade de compra × unidade de consumo** (resma → folha, rolo → m², kg → g) com fator de conversão.
- **Ficha técnica** por produto calculado: lista de insumos e consumo por unidade/m², com perda padrão.
- **Baixa automática por OS**: ao iniciar ou concluir a produção (configurável), baixa os insumos conforme a ficha técnica; o consumo real pode ser ajustado no apontamento.
- **Lote** (opcional por insumo): rastreio de entrada, saldo por lote.
- **Sobras e retalhos**: cadastro de sobras reutilizáveis (papel, vinil, lona) com dimensões; sugestão de uso na OS seguinte.
- **Estoque mínimo e ponto de pedido** por insumo, integrado à reposição e à geração de pedido de compra.
- **Inventário**: contagem, ajuste e justificativa, com kardex.

### 3.5 Arte, Prova e Aprovação (`arte`)

- **Anexos na OS e no orçamento** (PDF, imagens, ZIP) com **versionamento** (v1, v2…), autor e data. Extensões executáveis bloqueadas.
- **Verificação básica de arquivo** (pré-flight leve): resolução, dimensões × formato do produto, presença de sangria, perfil de cor; resultado informativo (aviso, não bloqueio).
- **Prova**: envio da versão ao cliente por link; o cliente **aprova ou solicita ajuste** com comentário. A decisão registra data, hora e IP, e vincula-se à versão aprovada.
- **Status da OS** incorpora “Aguardando arte” e “Aguardando aprovação”; não inicia produção sem arte aprovada (regra configurável por produto).
- **Aprovação de orçamento por link**: o cliente abre o link, vê o documento “seguro para cliente” (3.2.3) e aprova com um clique; a aprovação converte o orçamento (opcionalmente) em OS.
- **Requisito de arquitetura**: links públicos exigem um ponto de entrada acessível pela internet. **Decidido (D-03, 26/10/2026): relay hospedado com token de uso único e expiração, implementado no M3 junto ao módulo `arte`**; o Local API Service nunca é exposto diretamente. (Fallback de aprovação presencial, registrado na análise, se o relay atrasar.)

### 3.6 Produção por Etapas e Terceirizados (`producao`)

- **Roteiro por produto**: etapas padrão (pré-impressão, impressão, corte, vinco, dobra, laminação, acabamento, expedição, **terceirizado**), editáveis por OS.
- **Fila por setor/máquina** com visão em lista e integração com o Kanban de Projetos (o cartão reflete a etapa atual da OS).
- **Apontamento** de início e fim por etapa, responsável, quantidade produzida, **perdas e refação** com motivo. Operação por QR code ou código de barras impresso na OS; funciona em tela touch simples (ver D-04).
- **Etapa “Terceirizado”**: enviado ao fornecedor (data), previsão de retorno, recebido (data), conferência de qualidade (ok / refação). Atraso de retorno gera alerta no sino. O recebimento alimenta o pedido de compra e a conta a pagar (3.7).
- **Agendamento** (existente) passa a sugerir datas a partir do prazo de entrega do fornecedor + prazo interno.
- **Capacidade**: indicador simples de carga por setor na semana (horas previstas × disponíveis).

### 3.7 Compras e Cotação (`compras`)

- **Pedido de compra** (modelo existente) sai do pós-MVP: criação manual, a partir da reposição de estoque ou a partir de item terceirizado aprovado (3.2.2).
- **Cotação a fornecedores** para insumos: solicitação, registro de propostas, comparativo e escolha.
- **Recebimento**: confirma entrada no estoque (com lote, se aplicável) e gera **conta a pagar** com vencimento conforme condição do fornecedor.
- **Terceirizados**: o pedido ao fornecedor usa o VF cotado; se o valor cobrado for diferente, a divergência é registrada e alimenta o custo real (3.3).
- **Histórico por fornecedor**: preço praticado, prazo cumprido, refações; base para avaliação interna.

### 3.8 Financeiro Completo (`financeiro`)

- **Cobrança**: geração de boleto e Pix (cobrança com QR) via gateway/banco; baixa automática por retorno; link de pagamento no documento ao cliente.
- **Cartão e maquininha**: registro por bandeira e taxa; recebível por parcela.
- **Comissões**: cálculo por vendedor (percentual do cadastro do funcionário) sobre vendas recebidas; relatório de fechamento.
- **Conciliação bancária** por importação OFX/CSV, com sugestão automática de correspondência.
- **Fluxo de caixa** realizado × projetado por dia, semana e mês.
- **DRE gerencial simplificado** e inadimplência (aging, cobrança, bloqueio opcional de novas OS).
- **Sinal/adiantamento** controlado desde o orçamento; “entregue” exige pagamento resolvido, com exceção por permissão.

### 3.9 Fiscal Completo (`fiscal`)

- **NFC-e** a partir do PDV e **NF-e** a partir de venda/OS, via gateway REST (Focus NFe como padrão, com adapter para outros). XML e DANFE armazenados por 5 anos ou mais, com backup.
- **NFS-e** (serviço): suporte por município via gateway, para os serviços gráficos sob encomenda tributados por ISS.
- **Produto × serviço**: a OS classifica cada item como mercadoria ou serviço para definir o documento fiscal; regra validada com o contador antes da implementação (decisão D-05).
- **Terceirizados**: registro da nota de entrada do fornecedor, vinculada ao pedido de compra.
- Contingência, cancelamento, carta de correção e inutilização.
- Exportação para contabilidade (XML e relatório de documentos).

### 3.10 Pós-venda e Reimpressão (`movimento`)

- **Repetir pedido**: a partir do histórico do cliente, cria nova OS/orçamento com os mesmos itens e arte aprovada, recalculando preços.
- **Refação**: OS filha vinculada à original, com motivo, responsável e custo, separando **erro da gráfica** de **erro do cliente**.
- **Registro de reclamação** com status e histórico por cliente.
- **Histórico do cliente**: OS, orçamentos, compras, valores e arte aprovada.

---

## 4. Telas Novas ou Alteradas

| Módulo | Tela | Estado alvo |
| --- | --- | --- |
| `movimento` | Orçamento (itens calculados, itens de fornecedor, visão do cliente) | Alterada |
| `movimento` | Cotações pendentes (fila de itens “Aguardando cotação”) | Nova |
| `configuracoes` | Precificação (percentuais, faixas, pisos, acréscimos) | Nova |
| `cadastros` | Produto calculado, ficha técnica, tabela por cliente | Nova |
| `custos` | Custo e margem por OS; orçado × realizado | Nova |
| `arte` | Arquivos e versões; prova e aprovação | Nova |
| `producao` | Fila por setor; apontamento; terceirizados em andamento | Nova |
| `compras` | Cotação de insumos; pedido de compra; recebimento | Nova |
| `estoque_avancado` | Sobras e retalhos; lotes; inventário | Nova |
| `financeiro` | Cobrança Pix/boleto; comissões; conciliação; fluxo; DRE | Nova |
| `fiscal` | Emissão e cancelamento; NFS-e | Alterada |
| `dashboard` | Margem, OS em atraso, terceirizados atrasados, cotações pendentes | Alterada |

---

## 5. Modelo de Dados (acréscimos)

- **Precificação:** `preco_parametro`, `preco_faixa`, `preco_cliente`, `produto_ficha_tecnica`, `produto_ficha_item`.
- **Orçamento/OS:** `orcamento_item` ganha `tipo` (próprio/fornecedor), `snapshot_preco` (JSONB); `orcamento_item_cotacao` (`fornecedor_id`, `vf`, `validade`, `prazo_dias`, `selecionada`, `anexo`); campos de snapshot `cp`, `vo`, `acrescimo_fornecedor_pct`, `markup_orcamento_pct`, `valor_ajustado`, `ajuste_motivo`, `ajuste_usuario`. *(Nota da análise: a tabela real hoje chama-se `ordem_servico_item` — mapear nomes antes de modelar.)*
- **Custos:** `os_custo` (material, terceiro, mão de obra, perdas), `terceiro_desembolso`.
- **Estoque:** `unidade_conversao`, `estoque_lote`, `sobra_retalho`.
- **Arte:** `arte_arquivo`, `arte_versao`, `arte_aprovacao`, `link_publico` (token, expiração, uso).
- **Produção:** `roteiro_etapa`, `os_etapa`, `apontamento`, `os_terceirizado` (envio, previsão, retorno, conferência).
- **Compras:** `cotacao_insumo`, `cotacao_proposta`; `pedido_compra` já existente.
- **Financeiro:** `cobranca`, `comissao`, `conciliacao_item`.
- **Auditoria:** `log_campo_sensivel` (append-only) para alterações de VF, percentuais e VO.

Todas as tabelas operacionais mantêm `filial_id`.

---

## 6. RBAC (atualizado)

Mantém os níveis Admin, Gerente, Operador e Caixa, com o acréscimo das **permissões por campo** da seção 3.2.3. Regra efetiva: `nível permite E módulo habilitado no plano E (quando o campo for sensível) permissão específica`. O Caixa nunca acessa campos de custo de terceiros. Bloqueio por tentativas, expiração de sessão e anti-lockout permanecem.

---

## 7. Requisitos Não Funcionais

| Requisito | Critério |
| --- | --- |
| Confidencialidade de custo | Nenhum dado de VF/CP/percentual/fornecedor em respostas, documentos ou exportações para perfis sem permissão (testado por varredura de rotas × perfis) |
| Precisão | Cálculos com `Decimal`; arredondamento centralizado e testado (exemplos da seção 3.2.1 como casos fixos) |
| Rastreabilidade | Alteração de preço, percentual, VF e valor final sempre registrada com usuário, data e motivo |
| Performance | Listagens < 1 s com até 50 mil registros; recálculo de orçamento com 50 itens < 300 ms |
| Concorrência | 5 estações sem lock indevido; controle otimista de versão em orçamento e OS (409) |
| Links públicos | Token aleatório, expiração, uso restrito ao documento; limite de tentativas; sem exposição do Local API Service |
| Arquivos | Validação de tipo, tamanho e hash; extensões executáveis bloqueadas; incluídos no backup |
| Backup | Banco e pasta de arquivos (arte, anexos, XML fiscal), com restauração testada em máquina limpa |
| Licenciamento | Mantido do v2.2: nunca revoga por indisponibilidade; tolerância 72 h; modo leitura |
| Idioma | Todos os textos em PT-BR |

---

## 8. Critérios de Aceite e Roadmap

### 8.1 Aceite — orçamento com fornecedor

- VF 100,00 → CP 230,00 → VO 243,80; VF 87,35 → CP 200,91 → VO 212,96.
- Mudar o percentual global não altera orçamento já salvo; o recálculo exige ação explícita e gera log.
- Orçamento com item “Aguardando cotação” não pode ser enviado ao cliente.
- PDF, link, impressão e mensagem ao cliente mostram apenas descrição e **valor total**; nenhuma linha com VF, CP ou fornecedor.
- Operador sem `ver_custo_terceiro` não vê VF/CP em nenhuma tela, rota ou exportação.
- Ajuste manual do VO exige justificativa e fica registrado.
- Aprovação do orçamento gera pedido de compra em rascunho e etapa “Terceirizado”; recebimento gera conta a pagar.
- Custo real da OS usa o desembolso efetivo; divergência em relação ao VF cotado é exibida.

### 8.2 Aceite — demais módulos

- Plano Essencial: PDV com caixa aberto e fechado; contas a receber simples; `custos`, `compras`, `producao`, `arte`, `financeiro`, `fiscal` respondem `403`.
- Plano Profissional: todos os módulos acima liberados, exceto `multifilial` e `api_integracao`.
- Ficha técnica baixa o insumo correto na produção; unidade de compra converte para consumo.
- Prova aprovada por link registra versão, data, hora e IP; OS não entra em produção sem arte aprovada quando a regra estiver ativa.
- NFC-e, NF-e e NFS-e emitidas em ambiente de homologação com XML armazenado.

### 8.3 Roadmap por marcos

| Marco | Entregáveis | Plano |
| --- | --- | --- |
| **M0** | Correção da matriz de planos; caixa e contas a receber simples no Essencial; validação de dependências entre módulos | Essencial |
| **M1** | Motor de precificação (3.1); orçamento com fornecedor e confidencialidade (3.2); permissões por campo | Essencial |
| **M2** | Custo real e margem (3.3); estoque por consumo (3.4); compras e cotação (3.7); **sobrescrita de percentuais por fornecedor/serviço (Q-04)** | Profissional |
| **M3** | Arte, prova e aprovação por link (3.5) — **com relay público D-03**; repetir pedido e refação (3.10) | Profissional |
| **M4** | Produção por etapas, apontamento e terceirizados (3.6) | Profissional |
| **M5** | Fiscal completo (3.9); financeiro completo (3.8) | Profissional |
| **M6** | Multi-filial; API de integração; integrações (WhatsApp, loja online) | Enterprise |

Ordem de prioridade: **M1 antes de qualquer outra entrega**, por ser o núcleo comercial e a regra de negócio específica do cliente.

---

## 9. Decisões e Perguntas em Aberto

| # | Item | Situação |
| --- | --- | --- |
| **D-01** | Plataforma: manter Python (v2.2) ou migrar para C#/.NET 10 (v2.3) | Proposta: entregar M0–M2 na plataforma atual e decidir depois, pois o v2.3 congela funcionalidade nova durante a migração. *Em aberto — com critério de decisão ao fim do M2 (análise §5)* |
| **D-02** | Módulo nativo de licença em C++ (v2.3) | Proposta: tratar como opcional; o próprio PRD v2.3 registra ausência de evidência de pirataria |
| **D-03** | Ponto de entrada público para links de aprovação | **✅ Decidido (26/10/2026): relay hospedado com token de uso único, no M3 junto ao módulo `arte`; Local API Service não exposto** |
| **D-04** | Chão de fábrica (tablet/QR) | Proposta: tela de apontamento simples no desktop via QR na OS; web leve fica para avaliação |
| **D-05** | Classificação fiscal produto × serviço | Validar com o contador antes de modelar os campos (não trava M1) |
| **Q-01** | Os 130% e os 6% são acréscimos sobre a base anterior (VF × 2,30 × 1,06)? | **✅ Decidido (26/10/2026): sim, markup** — "VF + 130% é custo; custo + 6% é markup". A alternativa `VO = CP ÷ 0,94` está descartada; parâmetro renomeado para `markup_orcamento_pct` |
| **Q-02** | O VF informado já inclui frete e impostos do fornecedor? | Assumido como sim; alternativa: campo separado somado ao VF antes da fórmula |
| **Q-03** | Orçamento misto (itens próprios + fornecedor): itens próprios mostram valor unitário ao cliente? | Assumido: cliente vê descrição e **somente o total geral** |
| **Q-04** | Os percentuais variam por fornecedor ou por tipo de serviço? | **✅ Decidido (26/10/2026): sobrescrita opcional, no M2** (fora do escopo do M1) |

---

## 10. Glossário

| Termo | Definição |
| --- | --- |
| **VF** | Valor do fornecedor: total cobrado pelo fornecedor pelo serviço cotado |
| **CP** | Custo de produção gerencial: `VF × 2,30` |
| **VO** | Valor do orçamento: `CP × 1,06`; único valor informado ao cliente |
| **Visão do cliente** | Documento externo gerado no servidor, sem campos de custo |
| **Item terceirizado** | Item do orçamento/OS executado por fornecedor |
| **Desembolso real** | Valor efetivamente pago ao fornecedor |
| **Ficha técnica** | Lista de insumos e consumo por unidade de produto |
| **Entitlements** | Plano, limite de estações e módulos habilitados emitidos pelo RedGest |
