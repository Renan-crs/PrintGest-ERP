# Revisão UI/UX — Tela de Ativação de Licença (out/2026)

**Escopo**: AtivacaoWindow (primeira execução, modo Servidor), PRD v2.3 §4/§5.1.
Stack atual Qt/PySide6 + QSS; alvo da migração WPF/.NET 10 (tokens em
`docs/design_tokens.md`).

**Método**: as skills `dickwu/apple-design-skill` e
`nextlevelbuilder/ui-ux-pro-max-skill` não estão instaladas no ambiente — os
critérios aplicados são os resumidos no brief (lente apple-design como
princípios, sem importar padrões visuais do macOS; ordem do ui-ux-pro-max:
acessibilidade → interação → demais). A `image.png` enviada não pôde ser lida
(este modelo não tem entrada de imagem): o trabalho partiu do inventário
fornecido + medições diretas no código (probe de geometria ofscreen), que
confirmaram os achados antes da correção.

## Resumo do redesenho (implementado)

Coluna única centralizada com bloco de 560 px (P1 — padrão): marca, título
"Ativar o PrintGest", subtítulo de uma frase, progresso não interativo
"Passo X de 3 · <etapa>" com pontos de estado, cartão com o formulário do
contrato ativo, rodapé com diagnóstico automático do servidor local e a
garantia de 72 h em texto neutro. "Como funciona" e "Função deste computador"
viraram **Detalhes técnicos** recolhidos, em linguagem do usuário. Ao ativar:
espera com barra indeterminada + Cancelar; no sucesso, resumo (plano e
validade) e botão **Entrar**.

## Achados e correções (A1–F4)

| ID | Status | Correção aplicada |
| --- | --- | --- |
| A1 | ✅ | Botões "Ativar licença (F10)", "Testar conexão" e "Sair (Esc)" com rótulo visível, `minimumHeight(40)`, atalho no próprio rótulo e `accessibleName` (testado) |
| A2 | ✅ | Sem alturas fixas; textos por conteúdo com quebra automática. **Dois bugs** confirmados por probe e corrigidos: (1) alinhamento por item desliga o `heightForWidth` do QLabel — resolvido centralizando o **bloco** de 560 px; (2) mesmo sem alinhamento, layouts comprimem labels de múltiplas linhas abaixo da altura necessária — resolvido com `EtiquetaQuebra` (`ui/widgets.py`), que impõe `minimumHeight = heightForWidth(largura)` a cada resize. Probe nas 3 resoluções, incluindo detalhes abertos: zero cortes |
| A3 | ✅ | Contraste medido (15 pares, todos ≥ mínimo — tabela abaixo); placeholder no cinza secundário (5,07:1); borda de campo da ativação `#8E8E93` (3,26:1); tarja laranja removida (C8) |
| A4 | ✅ | Rótulos em sentence case, 13 px/600, cor de texto (`#rotuloCampo`) |
| A5 | ✅ | Corpo 12–13 px nos auxiliares (herda 13 px do QSS); escalas 125/150 % renderizadas em screenshot |
| A6 | ✅ | Ordem de Tab (CNPJ → código → Ativar → Testar → Sair → Detalhes → Tentar), Enter e F10 ativam, Esc sai com confirmação (D5), anel de foco de 2 px escopado aos campos da tela (`formAtivacao`) |
| A7 | ✅ | Marca desenhada em código, `accessibleName` vazio (decorativa); sem emoji |
| B1 | ✅ | Escala 4/8/24: rótulo→campo 4 px, entre grupos 24 px (constantes no código) |
| B2 | ✅ | Ações em linha: Sair à esquerda, Testar conexão + Ativar à direita; sem vazios de ~70 px (stretch dentro do cartão controlado) |
| B3 | ✅ | Uma única coluna centralizada (P1); bases/topos alinhados por construção |
| B4 | ✅ | Subtítulo sem quebras manuais, largura do bloco 560 px |
| B5 | ✅ | Monoespaçada apenas no valor digitado da chave (Contrato C) |
| B6 | ✅ | Estados definidos no QSS: hover, foco (2 px), desabilitado, erro (borda 2 px vermelha), carregando (barra + Cancelar) |
| B7 | ✅ | Probe nas 3 resoluções: nenhum widget fora da janela, sem corte (validação programática + screenshots) |
| C1 | ✅ | Passos e formulário seguem o contrato ativo: B = "Dados da licença" (CNPJ + código), C = "Chave de produto" (XXXX-XXXX-XXXX-XXXX) — testado |
| C2 | ✅ | Jargão fora da superfície: "Nó", "Host principal", "Local API Service", "Contrato B", "hexadecimais", "Tolerância Offline" removidos; conteúdo técnico em Detalhes técnicos, em linguagem simples (testado com varredura de termos proibidos) |
| C3 | ✅ | PT-BR revisado ("às estações" não ocorre mais — subtítulo reescrito sem o trecho) |
| C4 | ✅ (24/10) | Canal confirmado pelo responsável: **portal + e-mail**. Placeholder "Informe o código enviado por e-mail"; Detalhes técnicos: "O código é enviado por e-mail e também fica disponível no portal de licenças do fabricante" |
| C5 | ✅ | Superfície reduzida a: uma frase de subtítulo, uma linha de ajuda, rodapé de diagnóstico, uma linha de garantia |
| C6 | ✅ | Erro por campo (rótulo vermelho + borda 2 px + foco) e erro geral junto dos campos; mensagens do servidor já vêm em PT-BR do backend (409/502/503/limite/chave inválida); foco vai ao campo relacionado quando a mensagem o menciona |
| C7 | ✅ | Sentence case em títulos ("Sobre a licença", "Este computador") |
| C8 | ✅ | "Se a internet cair, o sistema continua funcionando por até 72 horas." — texto neutro, sem tarja de alerta |
| D1 | ✅ | Progresso não interativo: "Passo X de 3" + pontos (feito/atual/pendente); passo 3 mostra resumo (plano, validade) e "Entrar" |
| D2 | ✅ | **Cancelamento real (24/10)**: a ativação roda num cliente `httpx` dedicado (`Api.cliente_para_ativacao`, timeout 95 s) e Cancelar **fecha o cliente — a requisição em pleno voo é interrompida** — e invalida o token da tentativa: qualquer resposta já em curso é descartada, e uma nova tentativa nunca recebe resultado de outra. Se o servidor já tinha ativado, uma nova tentativa devolve a situação atual |
| D3 | ✅ | "Servidor local: conectado/sem resposta" testado automaticamente ao abrir + "Tentar novamente" |
| D4 | ✅ | Máscara de CNPJ + dígito verificador em linha (blur e envio), vazio não grita; código normalizado sem espaços ao colar; chave cola/formata sozinha |
| D5 | ✅ | Esc pede "Sair do PrintGest?" (default Não); durante a validação, Esc não abandona |
| D6 | ✅ (24/10) | Modo Estação implementado: `PRINTGEST_API_URL` liga o modo; a tela inicial é **Conectar ao servidor** (`ui/conexao.py` — endereço + teste + conectar, sem serial: a licença pertence ao servidor). Endereço persistido (QSettings) |
| D7 | ✅ | Painel "Detalhes técnicos" expande/recolhe com 160 ms (OutCubic), **respeitando a preferência do Windows** ("animar controles" lida via SPI_GETCLIENTAREAANIMATION); estados hover/foco permanecem trocas imediatas (QSS não suporta transição) |
| E1 | ✅ | Tokens consolidados em `docs/design_tokens.md` (claro/escuro/uso) + mapeamento WPF; sem hex cru em componentes (QSS por token) |
| E2 | ✅ (25/10) | **Marca oficial do cliente** (`printgest_logo`): símbolo "mira" (`printgest-simbolo.svg`) nas telas de ativação/conexão, ícone do produto (`printgest-icone.svg` → `printgest.ico` 16–256 px) no exe, no instalador e na taskbar (`app.setWindowIcon`). Fallback desenhado em código quando o plugin de SVG não existe. Logotipos horizontal/mono/negativo também em `ui/assets` para uso futuro (login/tema escuro) |
| E3 | ✅ (P2) | Sem filete CMYK (decisão P2: não incluir). Visual ancorado no design system existente (cartões claros, hairline), sem pílulas coloridas na superfície |
| F1 | ✅ | F10/Esc preservados; 3 passos; formulário dinâmico por contrato |
| F2 | ✅ | Timeout ≥ 90 s no cliente (95 s); mensagens de indisponibilidade vêm do backend (503 nunca revoga lá) |
| F3 | ✅ | Rótulo acima do campo, sem texto cortado, PT-BR; render em 100/125/150 % verificado por screenshot |
| F4 | ✅ | Nenhum log novo; CNPJ/código nunca viram log do desktop; segredos continuam no cofre do SO (backend) |

## Relatório de contraste (medido — `desktop/tools/contraste_ativacao.py`)

| Par (claro) | Razão | Mínimo | Resultado |
| --- | ---: | ---: | --- |
| texto #1D1D1F / canvas #F5F5F7 | 15,46:1 | 4,5 | OK |
| texto #1D1D1F / surface #FFFFFF | 16,83:1 | 4,5 | OK |
| muted #6E6E73 / canvas | 4,66:1 | 4,5 | OK |
| muted #6E6E73 / surface (ajuda, placeholder) | 5,07:1 | 4,5 | OK |
| ação #0066CC / canvas (botões planos) | 5,11:1 | 4,5 | OK |
| branco / primary #0071E3 (botão primário) | 4,70:1 | 4,5 | OK |
| texto / surface (botão secundário) | 16,83:1 | 4,5 | OK |
| erro #D70015 / surface | 5,38:1 | 4,5 | OK |
| sucesso #1B7031 / surface | 6,16:1 | 4,5 | OK |
| borda-campo #8E8E93 / surface | 3,26:1 | 3,0 | OK |
| foco #0071E3 / surface (anel 2 px) | 4,70:1 | 3,0 | OK |
| erro / surface (borda de estado) | 5,38:1 | 3,0 | OK |
| primary / canvas (ponto atual) | 4,31:1 | 3,0 | OK |
| sucesso / canvas (ponto feito) | 5,66:1 | 3,0 | OK |
| borda #D8D8DC / canvas (ponto pendente) | 1,31:1 | — | sem exigência: estado carregado no texto "Passo X de 3" |

Tokens novos em relação ao tema anterior: `acao` (#0066CC — texto de ação sobre
canvas; o primary #0071E3 dava 4,34:1, abaixo de 4,5:1) e `borda-campo`
(#8E8E93 — borda de campo ≥ 3:1; a hairline #D8D8DC dava 1,35:1). A hairline
das demais telas foi mantida (escopo da revisão é a ativação; mudança global
ficaria para uma revisão própria).

## Validação executada

- **Testes**: 28 na tela (`desktop/tests/test_ativacao.py` — estados, máscaras,
  CNPJ, confirmação de saída, acessibilidade, textos, layout, cancelamento
  real), 9 na tela de conexão (`test_conexao.py`), 1 no roteador de estação
  (`test_main.py`); suíte completa **311 passed / 0 failed** (sem regressão em
  Login, Modo leitura, Início, PDV, Projetos e Cadastros).
- **Probe de layout** (ofscreen, 1280x720, 1366x768, 1920x1080, nas DUAS telas
  e com detalhes abertos): nenhum widget fora da janela, nenhum label cortado,
  botões ≥ 40 px, cartão ≤ 560 px.
- **Screenshots** (`desktop/tools/render_ativacao.py` + `render_conexao.py` —
  gitignored, 12 arquivos): estados inicial/erro/validando/sucesso/detalhes do
  Contrato B, inicial do Contrato C, nas três resoluções e escalas 100/125/150,
  mais inicial/erro da tela de conexão.

## Decisões (P1–P6) — fechadas em 25/10/2026

- **P1 Layout**: coluna única (adotada). Alternativa de duas colunas descartada.
- **P2 Filete CMYK**: não incluir (adotado).
- **P3 Rótulos**: "Ativar licença", "Testar conexão", "Sair" — confirmados.
- **P4 Canal do código**: **portal + e-mail** (confirmado pelo responsável).
- **P5 Modo Estação**: **implementado** — `ui/conexao.py` + `PRINTGEST_API_URL`
  (endereço + teste + conectar; serial não é pedido; endereço persistido em
  QSettings; `_Roteador(estacao=True)` abre o login direto).
- **P6 Tema escuro**: só tokens (proposta medida em `docs/design_tokens.md`),
  sem implementação — segue a decisão do brief.

## Pendências e limitações

1. Hover/foco continuam trocas de estado sem animação (limite do QSS); o
   movimento do painel "Detalhes técnicos" cobre o D7 com 160 ms e respeita a
   preferência do Windows de reduzir animações.
2. Narrador: `accessibleName`/ordem de Tab implementados; validação assistida
   com leitor de tela fica como passo manual de QA (não automatizável aqui).
3. O instalador ainda só empacota o **modo Servidor**; a instalação de uma
   estação (definir `PRINTGEST_API_URL` no `.env` dela) é operação manual por
   enquanto — empacotar a estação fica para a fase de rede (PRD).
4. Logotipo: marca oficial do cliente aplicada (símbolo + ícone); os
   logotipos horizontal/mono/negativo ficam em `ui/assets` para o login e o
   tema escuro.
5. Os screenshots são para inspeção humana — o modelo não lê imagens; a
   verificação de corte/regressão foi programática (probe + testes).

## Tela do modo Estação (D6/P5, adicionada em 25/10)

`ConexaoWindow` (`ui/conexao.py`): mesma linguagem visual da ativação —
coluna única de 560 px, marca, "Conectar ao servidor", campo "Endereço do
servidor" (normaliza `192.168.0.10:8000/` → `http://192.168.0.10:8000`),
erro junto do campo, botões **Conectar (F10)** / **Testar conexão** / **Sair
(Esc)** ≥ 40 px, status "Servidor: conectado/sem resposta", confirmação ao
sair. O endereço usado com sucesso é persistido (QSettings) e volta
preenchido. No `main.py`, `PRINTGEST_API_URL` liga o modo: a tela de conexão
abre no lugar do gate de serial e o login vai direto ao servidor da gráfica
(a licença pertence ao servidor; modo leitura continua sendo aplicado lá).
