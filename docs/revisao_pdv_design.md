# Revisão UI/UX — PDV (Venda de Balcão) — resposta à Fase A (out/2026)

**Escopo desta entrega**: Fase A do roadmap proposto (itens 1–8 e 17) no stack
atual (Qt/QSS), preservando tudo o que já melhorou desde a v0.2.0 (busca em
largura útil, combos legíveis, "Consumidor final" padrão, menu na altura,
checkboxes com borda, F9/Esc e as duas visões — nenhum regresso).
Itens 9–16, 18–21 e as ideias §6 ficam para a Fase B (reorganização no WPF).

## Status dos itens

| # | Item | Status | O que foi feito |
| --- | --- | --- | --- |
| 1 | Estado vazio da lista | ✅ | QStackedWidget: sem itens mostra "Busque um produto ou serviço para adicionar" + atalhos (Ctrl+F busca · F9 finaliza · Esc descarta) + dica de Item avulso; com itens a tabela volta |
| 2 | Tabela de itens | ✅ | **Desconto por item** ganha coluna editável (contrato `VendaItemIn.desconto` já existia — só não aparecia na UI); **Total/Desc alinhados à direita**; cabeçalho e corpo na **fonte única** (ver nº 8). Remover (✕) e edição de Qtd/Unit já existiam e seguem. **Dimensões não entram**: decisão da spec C9 — largura × altura pertence ao fluxo de O.S.; a venda não tem esses campos no contrato |
| 3 | Campo de busca | ✅ | Placeholder curto ("Código, nome ou código de barras"), chip "Enter" removido; **código de barras exato adiciona direto** (EAN indexado); **vários candidatos abrem a lista navegável** (↑/↓ + Enter) em vez do aviso "não encontrado"; foco volta à busca após adicionar |
| 4 | Finalizar com 0 itens | ✅ | Confirmado no código (ficava habilitado). Agora **desabilitado** com tooltip "Adicione ao menos 1 item"; habilita ao adicionar; modo leitura desabilita com motivo |
| 5 | Faixas cinza | ✅ | Causa raiz: `QWidget { background: canvas }` pintava os wrappers de rótulo e os QCheckBox. Wrappers do PDV agora `#caixaForma` (transparente) e **QCheckBox/QRadioButton transparentes no QSS global** (mata a reincidência em todas as telas) |
| 6 | Combos | ✅ | Seta substituída por **SVG embutido** (`seta-combo.svg`, `%asset_seta%`) — a nativa renderizava a barra escura; Vendedor com **placeholder "Selecione o vendedor"** e sem seleção silenciosa. O padrão "funcionário vinculado ao usuário logado" fica pendente: não há vínculo usuário↔funcionário no modelo (ver D10) |
| 7 | Hierarquia do total | ✅ | Bloco **Subtotal / Desconto / Total** com o Total em **28 px** (`#totalPdv`), **colado à barra de ações** (nada entre eles); **"Falta R$ X"** em cor de aviso quando o recebido (digitado) não cobre; sem valor digitado não grita (fluxo atual não exige recebido) |
| 8 | Contraste e tipografia | ✅ | Contraste medido (tabela abaixo). **Fonte única**: a família é resolvida na inicialização (`Inter` → `Segoe UI` se ausente) e aplicada ao QSS e ao app — era o "fallback por widget" que fazia o cabeçalho cair numa serifa; o Total perdeu o fallback Consolas (monoespaçada permanece só no valor digitado da chave de produto, onde é desejável). Placeholder dos campos no cinza secundário (palette global) |
| 17 | Círculo translúcido sobre "Nova OS/Orçamento" | ✅ verificado | Nenhum efeito/sobreposição no código (varredura por `graphicsEffect` — nenhum nos botões); compatível com artefato da captura (cursor/indicador). Se aparecer no app, é bug de sobreposição a reportar com passo a reproduzir |

## Contraste medido (WCAG 2.1)

| Par | Razão | Mínimo | Resultado |
| --- | ---: | ---: | --- |
| aviso "Falta" (#B25000) / branco | 5,20:1 | 4,5 | OK |
| rótulos/rodapé (#6E6E73) / branco | 5,07:1 | 4,5 | OK |
| rótulos (#6E6E73) / canvas | 4,66:1 | 4,5 | OK |
| placeholder (#6E6E73) / branco | 5,07:1 | 4,5 | OK |
| texto (#1D1D1F) / branco | 16,83:1 | 4,5 | OK |
| texto / canvas | 15,46:1 | 4,5 | OK |
| "Finalizar" (branco / #0071E3) | 4,70:1 | 4,5 | OK |

## Validação

- **Testes**: 15 novos no PDV (estado vazio, placeholder/chip, bipe por EAN,
  lista navegável em resultados múltiplos, Finalizar desabilitado, desconto
  por item no total e no payload, alinhamento, Falta/Troco, resumo com
  desconto, resumo colado às ações, wrappers transparentes, placeholder do
  vendedor, fonte única, seta SVG, sem efeitos sobre o botão). Suíte completa:
  **339 passed / 0 failed** (inclui os testes de layout em 1920/1366/1280/
  960/853 que continuam verdes — sem regressão de largura).
- **Screenshots** (`tools/render_pdv.py`): `pdv_vazio_1920x1080`,
  `pdv_com_item_1920x1080` e `_1366x768` — o com_item mostra o estado
  "Falta R$ 95,80" com dois itens e o bipe EAN.

## Decisões pendentes (padrões sugeridos mantidos, nenhum implementado além)

| ID | Decisão | Situação |
| --- | --- | --- |
| D1 | "Pagamento já recebido" | Mantido por enquanto: é exigido pelo fluxo de sinal/condição do cliente (`CondicaoPagamentoCliente`). Remover depende de mover venda a prazo para O.S./Contas a receber (Fase B, quebra de UX validada antes) |
| D2 | Limite de desconto por perfil | Pendente de valor do responsável; sem limite hoje (o desconto por item novo também não limita) |
| D3 | Pagamento misto | Backlog (M6) |
| D4 | Caixa fechado | Não há módulo de caixa aberto/fechado no backend; bloqueio fica para a fase financeira |
| D5 | Venda em espera | Backlog; no MVP, memória da estação |
| D6 | Estoque insuficiente | Hoje não valida estoque no PDV; aviso-com-permissão quando houver consulta de saldo na busca (Fase B/§6.3) |
| D7 | Favoritos automáticos × marcados | Pendente (exige campo em produto — Fase C) |
| D8 | Multiplicador `3*código` | Backlog (conflito com EAN contendo `*` a validar) |
| D9 | Item repetido soma na linha | **Comportamento atual**: cada adição cria linha nova (contrato aceita); somar é melhoria de Fase B |
| D10 (novo) | Vínculo usuário ↔ funcionário | Necessário para o padrão do Vendedor sugerido ("funcionário do usuário logado") — campo no modelo, a decidir com o backend |

## O que fica para a Fase B (reorganização, WPF/M2)

Itens 9–16 e 18–21: separação de visão/ação na barra superior, R$ dentro do
campo com máscara, formas de pagamento segmentadas, revisão do
"Pagamento já recebido" (D1), "Descartar venda" com confirmação, compactação
vertical, botão "+" de cliente na hora, atalhos da tela no rodapé, feedback de
linha adicionada, "Caixa aberto desde", favoritos/mais vendidos e densidade
compacta em Preferências.
