# Changelog

Histórico de versões do **PrintGest ERP**. Formato inspirado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento
semântico.

As versões correspondem a tags anotadas neste repositório; o commit de destino
de cada tag está indicado para rastreabilidade.

---

## [0.3.1] - 2026-10-30 · Sistema de atualização, helpers de UI, refatoração

### Novos Recursos
- **Sistema de notificação de atualização (M3 §3.11):** widget `NotificacaoAtualizacao`
  com aparência não bloqueante, visível e acessível. Endpoint `POST /v1/atualizacao/verificar`
  no backend e método `api.verificar_atualizacao()` no cliente desktop.
- **Auto-assinatura gratuita:** script `scripts/empacotar_autosign.ps1` para gerar certificado
  auto-assinado e empacotar com assinatura digital. Útil para testes internos, mas
  o SmartScreen ainda pode mostrar aviso (necessário certificado pago para eliminação completa).
- **Helper methods para estados visuais:** novos helpers em `widgets.py`:
  `estado_sucesso()`, `estado_erro()`, `estado_atencao()`, `estado_muted()`,
  `estado_ghost()`, `estado_secundario()`, `estado_primario()`, `aplicar_estado()`.

### Refatoração
- **Helpers de UI:** substituições de `setProperty("role", ...)` por helpers em:
  - `desktop/printgest/ui/tela_principal.py` (22 ocorrências)
  - Padronização de estados visuais para consistência e manutenibilidade

### Adicionado
- **M3 §3.10 — repetir pedido e refação:** endpoints `POST /v1/os/{id}/repetir` e `POST /v1/os/{id}/refacao` com integração de status de OS. Repetir duplica itens e arte aprovada (preços calculados do catálogo). Refação cria OS filha com campos `refacao_motivo`, `refacao_responsavel_id`, `refacao_custo`, `refacao_erro` (Grafica ou Cliente). Tabelas `arte_versao`, `arte_aprovacao`, `link_publico` (migração `b0c1d2e3f4a5`, aditiva e reversível). NFR de arquivos: extensões executáveis bloqueadas (`.exe`, `.bat`, `.dll`, `.js`…), máximo 50 MB, arquivo vazio rejeitado, hash SHA-256 gravado para integridade. 

### Corrigido
- **M3 — backend de arte, prova e aprovação (PRD v3.0 §3.5):** upload de arte com **versionamento** (v1, v2… por O.S., auto-incremento), **decisão do cliente** (`aprovada`/`ajuste` com comentários obrigatórios — registra data, hora e IP), **estados derivados** (`sem_arte` → `aguardando_aprovacao` → `aprovada`/`ajuste_solicitado`) e **link público** com token aleatório e expiração (uso único; o relay hospedado da decisão D-03 resolve o token no futuro). Tabelas `arte_versao`, `arte_aprovacao`, `link_publico` (migração `b0c1d2e3f4a5`, aditiva e reversível). NFR de arquivos: extensões executáveis bloqueadas (`.exe`, `.bat`, `.dll`, `.js`…), máximo 50 MB, arquivo vazio rejeitado, hash SHA-256 gravado para integridade. A **tela desktop** do módulo vem na v0.4.0. Backend 329 passed (+12).

### Novos Recursos
- **M3 §3.10 — repetir pedido e refação:** endpoints `POST /v1/os/{id}/repetir` e `POST /v1/os/{id}/refacao` com integração de status de OS. Repetir duplica itens e arte aprovada (preços calculados do catálogo). Refação cria OS filha com campos `refacao_motivo`, `refacao_responsavel_id`, `refacao_custo`, `refacao_erro` (Grafica ou Cliente).
- **Primeiro acesso funcionário:** campo `login` em `FuncionarioCreate` (fornecido pelo admin), flag `primeiro_acesso` em `Usuario`, endpoint `POST /auth/primeiro-acesso` para configuração de senha na primeira visita.
- **Desktop — rodapé com IP do servidor:** o rodapé agora exibe o IP do servidor extraído de `base_url`, facilitando identificação em redes locais sem IP dedicado.

### Corrigido
- **Paginador das telas de listagem (›| desalinhado na última página parcial):** o clamp usava `total − lote`, que só vale para página cheia — com 120 registros e lote 50, "última página" saltava para offset 70 (desalinhado) em vez de 100: a grade mostrava as linhas 71–120 rotuladas "Pág 2 de 3" e a navegação ‹/› seguinte andava de 20 em 20. O offset agora é contido à última posição válida e **alinhado ao múltiplo do lote**. Encontrado pela navegação sistemática exigida na validação de listagem/paginação.
- **Dependência do upload de arte:** `python-multipart` pinado em `requirements.txt` — sem ele, qualquer instalação limpa **não sobe** o serviço (o FastAPI falha no import das rotas com `File`). O pacote já existia no venv de dev; faltava o registro da dependência.

### Testes
- **Fumaça sistemática contra o servidor real** (`backend/scripts_fumaca.py`, **134 verificações** verdes em `:8000`): auth (401 sem/com token inválido), CRUD + busca + **paginação** (limit/offset/meta.total) de todos os cadastros, ciclo do caixa (abrir → suprimento → sangria → extrato → fechar; **venda bloqueada 409 com caixa fechado**), estorno de venda **restaurando estoque**, 409 de estoque insuficiente e cliente inexistente, O.S. (status, converter, 400 na re-conversão), cotações (lançar → selecionar → **snapshot VF/CP/VO** → estado `cotado`), **VF omitido para Operador** (§3.2.3) e 403 em config/precificação, terceirizado (auto-criado → receber → conferir), arte (upload v1 → `.exe` bloqueado → ajuste → reenvio v2 → aprovação → estados → link → 404), quadro de projetos (listas, cartões com controle otimista de versão, mover, comentários, checklists, etiquetas, atividade). **M2 e M4 validados em campo**.
- **Desktop:** 8 testes de Agendamento promovidos de `xfail` (a refatoração síncrona do `rodar` resolveu a limitação offscreen; 4 genuínos seguem marcados) e **7 testes novos de paginação** (`test_paginador.py`: primeira página 50 de 120, › busca offset 50 e troca as linhas, ›| parcial desabilita ›, |‹ volta, ‹ na primeira não dispara, estados do widget e sinal `mudou`). Desktop **371 passed** (antes 356).
- Runtime desversionado: `backend/uploads/` (arquivos de arte são dado de runtime, apontado por `arte_versao.caminho`) sai do git e entra no `.gitignore`.

---

## [0.3.0] - 2026-10-27 · PRD v3.0 — M0 (planos e caixa) + M1 (motor de precificação e orçamento com fornecedor)

### Adicionado
- **M1 — tela desktop do orçamento com item de fornecedor (PRD v3.0 §3.2.2):** `GradeItens` ganha **coluna "Tipo"** ("Próprio" / "Fornecedor • Aguardando" / "Fornecedor • Cotado") + checkbox **"Fornecedor"** na barra de edição; `item_selecionado` expõe os dados internos. `PaginaOrcamento` ganha botão **"Cotações" (F10)** que abre o `DialogoCotacoes` — QDialog completo com **comparativo em tabela** (VF/prazo/validade por linha, ✓ na selecionada), **formulário de lançamento** (fornecedor combo, VF, prazo, validade, observações, "Selecionar esta cotação"), botão **"Selecionar marcada"** para a linha da tabela, e bloco de cálculo **VF/CP/VO** (para Operador, VF mostra "(restrito)" — a API omite, não oculta). Api do desktop: `listar_cotacoes`, `lancar_cotacao`, `selecionar_cotacao`. Desktop 356 passed (+14).

### Documentação
- **Análise do PRD v3.0** (`docs/analise_prd_v3.md`): verificação das alegações de existência contra o código (caixa/contas/pedido_compra existem; gating por plano **não** existe — dependência RedGest a incluir no M0), validação da matemática VF→CP→VO com `ROUND_HALF_UP` (exemplos do PRD fecham exato; "VF × 2,438" diverge em borda e passa a "≈"), mapeamento `orcamento_item`→`ordem_servico_item`, saneamento `Mapped[float]`, 409 em orçamento/OS, recomendações D-01..D-05/Q-01..Q-04 e lente de design para as telas novas.
- **Decisões do PRD v3.0 registradas (26/10/2026)**: **Q-01 = markup** ("VF + 130% é custo; custo + 6% é markup" — `VO = CP × 1,06`; alternativa `CP ÷ 0,94` descartada; parâmetro renomeado para `markup_orcamento_pct`), **Q-04 = sobrescrita no M2**, **D-03 = relay com token de uso único no M3**. PRD atualizado nas seções 3.2.1, 3.5, 5, 8.3 e 9.

### Adicionado
- **M1 — aprovação gera pedido de compra em rascunho (PRD v3.0 §3.2.2 item 7):** ao aprovar o orçamento (converter em OS), cada fornecedor com cotação selecionada recebe um `pedido_compra` **ABERTO/rascunho** ligado à OS (`os_origem_id`), com o **VF cotado** no item (nunca vai ao cliente); a cotação recebe `pedido_item_id` (recebimento fecha o ciclo em §3.7). Itens da OS nova copiam `tipo` e `snapshot_preco`; `estado_cotacao` deriva do snapshot (as cotações ficam no orçamento para auditoria). **Bloqueio**: aprovar com item de fornecedor sem cotação selecionada responde `409` com orientação. `pedido_compra_item.produto_id` nullable (serviço terceirizado não é produto do catálogo; migração `e7f8a9b0c1d2`, aditiva e reversível). Backend 307 passed (+3).
- **M1 — item de fornecedor e cotações na OS/Orçamento (PRD v3.0 §3.2.2/§3.2.3):** `ordem_servico_item` ganha `tipo` (`proprio` | `fornecedor`) e `snapshot_preco` (JSONB); nova tabela `os_item_cotacao` (VF, validade, prazo, observações, **uma** selecionada por item — índice único parcial; migração `d6e7f8a9b0c1`, aditiva/reversível). Fluxo: item terceirizado nasce **"Aguardando cotação"** (valor 0); Gerente/Admin lança cotações (`POST /v1/os/{id}/itens/{id}/cotacoes`); selecionar (`PUT .../selecionar`) assume o **VO calculado** como valor do item, grava o **snapshot** (VF, percentuais, CP, VO) e reprocessa os totais da OS. Comparativo interno (`GET`): VF/prazo/validade. **Confidencialidade §3.2.3**: `ver_custo_terceiro` = Admin/Gerente — as respostas para Operador **omitem** `vf` e o snapshot (chave nem existe), cotação/ajuste exigem nível ≥ Gerente (Caixa nem entra no router de OS). Estados derivados `aguardando`/`cotado` em `OsItemOut.estado_cotacao`. Backend 304 passed (+5).
- **M1 — motor de precificação, núcleo (PRD v3.0 §3.2.1):** `app/services/precificacao.py` com a regra VF→CP→VO decidida (Q-01: markup) — `CP = VF × 2,30`, `VO = CP × 1,06`, `ROUND_HALF_UP` explícito (o padrão *banker's* do Decimal daria 200,90 no caso canônico 87,35), **fórmula normativa sequencial** (CP arredondado antes do VO; o atalho VF × 2,438 é ≈ e diverge em borda) e **snapshot** do item terceirizado (VF, percentuais, CP e VO como texto — mudar o parâmetro não altera itens já orçados). Parâmetros globais por filial em `preco_parametro` (migração `b5d6e7f8a9c0`, aditiva/reversível; defaults 130/6; registra quem/quando alterou) com endpoint **Admin** `GET/PUT /v1/config/precificacao` (permissão `alterar_parametros_precificacao`). Os exemplos do PRD viraram **casos fixos de teste** (100→230,00→243,80; 87,35→200,91→212,96; borda 0,05→0,13). Sobrescrita por fornecedor/serviço fica no M2 (Q-04).
- **M0 do PRD v3.0 (planos e caixa):** gating de módulos por plano no servidor (`app/services/gating.py`) — rota de módulo fora do `entitlements.modulos` responde `403 MODULO_BLOQUEADO`, com mapa rota→módulo (caixa e contas a receber simples do Essencial casadas antes do restante do financeiro do Profissional); `MODULOS_HABILITADOS` recalculado junto ao estado da licença, "ausente/malformado não libera nenhum módulo"; **módulos vindos do RedGest persistidos nos dois contratos** (payload autoritativo: sem a lista, nada libera; formatos aceitos no topo ou dentro de `entitlements`); flag `PRINTGEST_GATING_MODULOS` (padrão desligada — arma quando o RedGest emitir `modulos`, mesma lição da `api_key`). **PDV não opera com caixa fechado**: `POST /v1/vendas` responde `409 "Caixa fechado"` sem caixa aberto para o vendedor logado; o desktop mostra banner "Caixa fechado — abra o caixa" com botão que leva à tela de abertura e reconfere ao voltar para a venda. Saneamento pré-M1: as 31 colunas `Numeric` anotadas como `Mapped[float]` agora são `Mapped[Decimal]` (a anotação induzia float no motor de precificação do M1). Backend 299 passed (+52), desktop 342 passed (+3).
- **PDV (revisão UI/UX — Fase A, docs/revisao_pdv_design.md):** estado vazio orientando no lugar dos ~600 px em branco; coluna de desconto por item na grade (o contrato `VendaItemIn.desconto` agora aparece na UI); Total/Desc alinhados à direita; busca com placeholder curto e sem chip "Enter", **código de barras exato adiciona direto** e **vários candidatos abrem a lista navegável**; Finalizar desabilitado com 0 itens ("Adicione ao menos 1 item"); faixas cinza atrás de rótulos/checkboxes eliminadas (QCheckBox/QRadioButton transparentes no QSS global — fim da reincidência); seta de combo em SVG embutido (sem a barra escura nativa) e Vendedor com placeholder; bloco Subtotal/Desconto/**Total 28 px** colado à barra de ações; **"Falta R$ X"** em aviso quando o recebido não cobre; **fonte única resolvida na inicialização** (Inter → Segoe UI — o "fallback por widget" fazia o cabeçalho de tabela cair numa serifa) e placeholder no cinza secundário. Contraste medido (7 pares >= mínimo).
- **Desktop (ativação, revisão UI/UX):** tela redesenhada em coluna única de 560 px (docs/revisao_tela_ativacao.md). Botões com rótulo e altura >= 40 px (F10/Esc no próprio texto), textos sem corte (dois bugs de altura corrigidos: alinhamento por item desativando o `heightForWidth` do QLabel e layouts comprimindo labels multilinha — novo `EtiquetaQuebra` impõe a altura mínima real), formulário coerente com o contrato ativo (B = CNPJ + código com dígito verificador em linha; C = chave XXXX-XXXX-XXXX-XXXX), erro por campo junto do campo, progresso não interativo "Passo X de 3" com resumo e "Entrar", **cancelamento real da validação** (cliente `httpx` dedicado fechado em pleno voo + token de tentativa descarta respostas superadas), Esc com confirmação, diagnóstico automático do servidor local, jargão fora da superfície, garantia de 72 h em texto neutro e canal do código confirmado (e-mail + portal). Contraste medido (15 pares >= mínimo; tokens novos `acao` #0066CC e `borda-campo` #8E8E93). Tokens claro/escuro + mapeamento WPF em `docs/design_tokens.md`. Cliente de ativação com timeout de 95 s (PRD §4.3).
- **Desktop (marca):** identidade visual oficial do cliente aplicada — símbolo "mira" nas telas de Ativação e Conexão, `printgest.ico` no `PrintGest.exe`, no `PrintGestAPI.exe`, no instalador e na taskbar; logotipos horizontal/mono/negativo em `ui/assets` para uso futuro; `.ico` regenerável por `desktop/tools/gerar_ico.py` (Pillow, só build).
- **Desktop (modo Estação):** tela **Conectar ao servidor** (`ui/conexao.py`, D6/P5) ativada por `PRINTGEST_API_URL` — endereço normalizado + teste + Conectar (F10), sem gate de serial (a licença pertence ao servidor), endereço persistido em QSettings e reutilizado. Painel "Detalhes técnicos" com expansão animada de 160 ms respeitando a preferência do Windows de reduzir animações.
- **Instalador (Estação):** `scripts\empacotar.ps1 -Modo estacao` gera `PrintGest-Setup-<versão>Estacao.exe` — apenas o desktop; o assistente pergunta o endereço do servidor e grava `.env` ao lado do exe (lido pelo `main._carregar_env_do_executavel`). Instalações de Servidor e Estação convivem (AppIds/pastas distintos).
- **Empacotamento/instalador:** pipeline de build versionado em `scripts/empacotar.ps1` + `installer/` (specs PyInstaller do backend e do desktop, script Inno Setup). Gera o `PrintGest-Setup-<versão>.exe` — instalação por usuário (sem UAC) com **desinstalador** que encerra o daemon, para o PostgreSQL embarcado e remove o cluster local. O `.env` da instalação vem de `installer/env.instalacao(.example)` — **não** do `backend\.env` de dev — e por padrão **não embute `api_key`** (Contrato B não usa; para Contrato C o build exige a chave preenchida no arquivo local, fora do git). Assinatura digital opcional via `-Assinar` (thumbprint ou `.pfx` + `signtool`, com carimbo de tempo). Arquitetura e operação documentadas em `docs/empacotamento.md`.
- **Backend (PostgreSQL embarcado):** `app/core/postgres_embarcado.py` prepara o cluster na primeira execução da instalação (initdb → pg_ctl start → CREATE DATABASE), ativado por `PRINTGEST_PG_EMBARCADO=true`. Host/porta/usuário/banco vêm do próprio `PRINTGEST_DATABASE_URL`.
- **Backend (exe congelado):** migrations Alembic passam a rodar pela API Python quando congelado (`sys._MEIPASS` resolve `alembic.ini`/`alembic/` do bundle) — o subprocesso `python -m alembic` só existe em dev.
- **Backend (entry point):** `run_server.py` carrega o `.env` ao lado do executável, anexa log em `logs/printgest-api.log` e serve o uvicorn sem reload.
- **Desktop (daemon):** `printgest/core/daemon.py` sobe o `PrintGestAPI.exe` instalado quando o `/health` não responde, com diálogo de espera na primeira execução (initdb); em dev nada muda.
- **Licenciamento:** suporte ao Contrato B v4.0 (RedGest `/api/v1/licencas/`) atrás da flag `PRINTGEST_REDGEST_CONTRATO=b`. Ativação por CNPJ + código, credenciais `client_id`/`client_secret` no cofre local, estado derivado com tolerância de 72 h. Contrato C permanece como padrão.
- **Desktop (ativação):** formulário dinâmico conforme o contrato retornado por `GET /v1/licenca` (CNPJ + código para Contrato B).
- **Desktop (instalação):** a tela de serial passa a ser o **gate de instalação**, exibida **antes do login** quando não há licença local. Depois de ativada, a licença fica gravada no Local API Service e o login abre direto o sistema; a tela só reaparece se a instalação for refeita (licença ausente). `scripts/limpar_licenca.py --sim` reproduz esse estado para teste; `desktop/tools/render_ativacao.py` gera a prévia visual.
- **Desktop (Dashboard):** revisão de design da Tela Inicial (Apple HIG + UI/UX Pro Max). Contraste do verde corrigido de 4,40:1 para 6,16:1 sobre branco; hierarquia de CTA (um primário + secundários); estado vazio com ação de recuperação em Entregas e Faturamento; séries do gráfico distinguíveis sem depender de cor, com legenda e valor exato; nomes acessíveis nos KPI, lista e barras. Registro em `docs/revisao_dashboard_design.md`.
- **Módulo Projetos (Quadro Kanban) — Fase 1 (Núcleo), backend.** Namespace novo
  `/v1/projetos`, **aditivo**: `/v1/os` e o quadro atual de Projetos seguem
  intactos. Quadro por filial com listas configuráveis e cartões, membros,
  movimentação **atômica** com ordenação fracionária (com rebalanceamento) e
  controle **otimista** de versão (409).
- Visibilidade **PV1–PV5 no servidor**: cartão sem membros é da equipe; com
  membros, restringe a membros + Admin/Gerente (cartão invisível → 404);
  contagens por lista respeitam a visibilidade do consultante.
- Migração `e7c1d4a2b9f6` (reversível): cria `quadro`, `quadro_lista`, `cartao`,
  `cartao_membro` e os enums `tipo_lista`/`origem_membro`.
- 20 testes novos em `backend/tests/test_projetos.py` (semente, CRUD de listas,
  cartões, mover/rebalancear, 409, PV1–PV5, RBAC, limpeza de campos com `null`,
  não-regressão). Backend: **142 testes** verdes.
- **Módulo Projetos — Fase 1 (Núcleo), tela do desktop.** A página *Projetos*
  passa a consumir `/v1/projetos`: colunas são as listas do servidor, cartões são
  a unidade (não mais "1 projeto = 1 O.S."), arrastar-e-soltar e menu "Mover para"
  gravam via `PATCH /cartoes/{id}/mover` (índice + versão), ficha do cartão
  (título, descrição, datas, lembrete, responsável, concluído, arquivar/restaurar
  e membros) e gestão de listas para gestores (Admin/Gerente; exclusão só Admin).
- `QuadroKanban.definir_colunas()` reconstrói as colunas a partir do servidor e o
  soltar passa a informar o **índice** de inserção (novo 3º argumento de `movido`,
  calculado pela metade do cartão), habilitando reordenação dentro da lista.
- 25 testes em `desktop/tests/test_projetos.py` cobrindo o quadro, a busca, a
  movimentação (índice/versão), o modo leitura, o RBAC de estrutura e os diálogos
  de cartão e de listas. Desktop: **240 testes** verdes.
- **Módulo Projetos — Fase 2 (cartão rico), modelo de dados.** Migração
  `f2a3b4c5d6e7` (reversível) cria `etiqueta`, `cartao_etiqueta`,
  `cartao_checklist`, `cartao_checklist_item`, `cartao_comentario` e
  `cartao_atividade`. Aditivo: nenhuma tabela existente muda (etiquetas por
  filial, checklists com itens, comentários em 1 nível e log append-only).
- **Módulo Projetos — Fase 2 (cartão rico), backend.** Sob `/v1/projetos`:
  catálogo de etiquetas por filial (RBAC de estrutura — Admin/Gerente criam,
  editam e excluem; Operador lê) e aplicar/remover na ficha do cartão
  (idempotente); checklists com itens (checkbox, responsável, data e ordenação
  fracionária) e progresso exposto no cartão (`checklist_total`/
  `checklist_concluidos`); comentários com resposta em **1 nível** (a segunda
  camada é recusada), edição pelo autor e **soft-delete** (autor ou gestor, a
  linha fica para não quebrar as respostas); e log de atividade **append-only**
  alimentado por todas as escritas (`criado`, `atualizado`, `movido`,
  `arquivado`, `membro_add`, `etiqueta_add`, `checklist_criado`,
  `item_concluido`, `comentario`, ...), consultável em
  `GET /cartoes/{id}/atividade`. Nenhuma dessas escritas incrementa `versao` —
  a versão otimista guarda título/descrição/datas, mover, arquivar e atribuir.
- 17 testes novos em `backend/tests/test_projetos_fase2.py` (RBAC de etiquetas,
  etiquetas no cartão, checklists/itens/progresso, reordenação, 404 de
  isolamento, comentários em 1 nível, autoria, soft-delete e moderação, log de
  atividade, RBAC do Caixa e bloqueio de escrita no modo leitura). Backend:
  **167 testes** verdes.
- **Licença por chave de produto (RedGest Contrato C).** A ativação deixa de
  trocar CNPJ + código por um JWT e passa a validar **online** a **chave de
  produto** (`XXXX-XXXX-XXXX-XXXX`) em `POST /api/v1/licencas-software/validar/`,
  autenticando por HMAC-SHA256 do `Sistema.api_key` (`X-RedGest-Signature` /
  `-Nonce`/`-Timestamp`). A licença local guarda `chave_ativacao`,
  `maquina_fingerprint` (SHA-256), `expira_em`, `limite_ativacoes` e
  `ativacoes_realizadas`; `expira_em` nulo = vitalícia. Não há mais JWT nem
  renovação antecipada: o RedGest é reconsultado a cada
  `licenca_revalidar_a_cada_segundos` (default 6 h) e é essa revalidação que
  detecta revogação, bloqueio e expiração.
- **Resiliência à indisponibilidade do RedGest.** Erro de rede na ativação/
  revalidação vira `503` (antes `500`); timeout de contato configurável
  (`licenca_timeout_segundos`, 90 s) e backoff progressivo no loop
  (`licenca_backoff_segundos`, 60/300/900 s). A licença ganha estados derivados
  (`ativa`/`tolerancia`/`leitura`/`revogada`/`nao_ativada`) e janela de tolerância
  offline de 72 h (`licenca_tolerancia_horas`), contada da vigência (`expira_em`):
  enquanto o RedGest estiver fora, o sistema **continua escrevendo**. Sem
  `PRINTGEST_REDGEST_API_KEY` a ativação responde `502` antes de qualquer chamada
  de rede.
- Migração `a1b2c3d4e5f6` (aditiva e reversível) acrescenta as colunas da chave de
  produto (`chave_ativacao`, `maquina_fingerprint`, `expira_em`,
  `limite_ativacoes`, `ativacoes_realizadas`) e afrouxa `cnpj`/`codigo_licenca`,
  além de manter `tolerancia_expira_em`/`ultima_tentativa_em`/`ultimo_erro`.
- Testes reescritos em `backend/tests/test_licenciamento.py` (o mock confere
  assinatura HMAC, nonce, timestamp e bytes do corpo; ativação, revogação,
  bloqueio, limite, vitalícia, tolerância e diagnóstico). `scripts/redgest_stub.py`
  ganha o endpoint do Contrato C e o desktop passa a pedir apenas a chave de
  produto. Backend: **183 testes** verdes.
- **Conformidade com o documento de integração do RedGest (v1.0, 18/10/2026).**
  O `maquina_fingerprint` passa a ser o SHA-256 do JSON canônico (chaves
  ordenadas) de identificadores **estáveis** de hardware — `bios_uuid`,
  `placa_mae_serial`, `cpu_id` e `disco_serial` via CIM/PowerShell — em vez de
  hostname + MAC. Assim o fingerprint não muda ao renomear a máquina ou
  reinstalar o PrintGest (sem consumir `limite_ativacoes` à toa); campos
  ausentes/genéricos são omitidos e há fallback estável e override por
  `PRINTGEST_MAQUINA_FINGERPRINT`. Mapa completo de conformidade em
  `docs/licenciamento_online_first.md` §6/§7.
- **Conformidade com o documento de integração do RedGest — rodada 2
  (§4.2/§9.2/§9.4).** Três lacunas fechadas: (a) o serial passa a ser aceito
  **com ou sem hífens** (e com espaços) e **validado localmente** antes de
  qualquer chamada de rede; (b) o backoff de revalidação ganha **jitter** de
  ±20 %; (c) a `chave_ativacao` deixa de ficar em texto puro no banco e passa a
  ser gravada no **cofre do SO** (DPAPI de escopo de máquina) — novo
  `backend/app/core/cofre.py`, coluna `Text` e migração `b2c3d4e5f6a7`.
- **Cofre do SO para a chave de ativação** (doc §9.4). `PRINTGEST_COFRE=dpapi`
  (default) cifra o serial com `CRYPTPROTECT_LOCAL_MACHINE` no formato
  `dpapi:v1:<base64>`: protege o arquivo do banco (backup/dump) sem amarrar o
  segredo ao usuário que ativou (o Local API Service pode rodar como serviço).
  `PRINTGEST_COFRE=nenhum` desliga (dev/diagnóstico) e fora do Windows o módulo
  degrada para texto puro com aviso no log. Linhas antigas (texto puro) seguem
  legíveis; blob ilegível (banco restaurado em outra máquina) vira `nao_ativada`
  e a UI pede a reativação, em vez de mandar lixo ao RedGest. Nada de sensível
  (`chave_ativacao`, `api_key`, `nonce`, assinatura) vai para o log.
- 12 testes novos: formato do serial (com/sem hífens, espaços, inválido sem
  tocar na rede, `_parse_chave`), jitter dentro da faixa, chave cifrada no banco
  e revalidação com a chave em claro, cofre (`backend/tests/test_cofre.py`:
  roundtrip, texto puro legado, blob corrompido, cofre desligado). Backend:
  **195 testes** verdes.
- **Banner progressivo de tolerância (doc de integração §9.3 / etapa E5).** Em
  `estado="tolerancia"`, a Tela Principal mostra um banner **não bloqueante**
  (âmbar, acima do cabeçalho) com a mensagem "Sem conexão com o servidor de
  licenças. O PrintGest continuará funcionando normalmente até DD/MM/AAAA HH:MM",
  o **tempo restante** ("Restam 2 dias e 21 h") e uma barra com a fração da
  tolerância ainda disponível. O countdown é recomposto a cada minuto por um
  `QTimer` **sem chamada de rede** (a situação é reconsultada pelos 5 min já
  existentes) e o banner sai de cena sozinho quando a revalidação volta a
  `ativa` — nenhuma escrita é bloqueada. Se o daemon local parar de responder, o
  aviso **permanece** (desconhecimento não é licença nova). Desktop: **256
  testes** verdes.
- **Suíte de aceite da resiliência (etapa E6).** O "cold start" passa a ser
  exercitado com atraso **real** (`_RedGestReal`: um socket local que dorme antes
  de responder), provando que `licenca_timeout_segundos` está de fato ligado à
  requisição: lento mas dentro do timeout → `200` sem erro visível
  (`test_cold_start_lento_conclui_sem_erro_visivel`); acima do timeout → `503`,
  sem revogar a licença e com recuperação automática quando o RedGest volta
  (`test_cold_start_estoura_timeout_real_e_recupera`). O "rollover de token" do
  plano vira rollover de **vigência** — o Contrato C não tem token:
  `test_revalidacao_renova_a_vigencia_e_reativa` (a revalidação com `expira_em`
  novo tira a instalação de `tolerancia` e volta para `ativa`, recalculando a
  janela) e a licença vitalícia permanece vitalícia. Os 5 aceites da §0 de
  `docs/plano_resiliencia_licenca.md` ganham mapa para testes nomeados e o E6
  fica marcado como **concluído**. Backend: **200 testes** verdes.
- **Plano de migração para o RedGest v4.x (`/api/v1/licencas/`).** Novo
  `docs/migracao_redgest_v4.md`: o `/licencas-software/` (Contrato C) é
  depreciado — passa a responder `Deprecation: true`,
  `Sunset: Mon, 01 Mar 2027` e `Link: .../licencas/; rel="successor-version"` —
  e o sucessor do PrintGest é o **Contrato B v4.0** na estratégia
  `hardware_bound` (ativação por `cnpj` + `codigo_licenca`, credencial
  `client_id`/`client_secret`, JWT RS256 com verificação local e
  `grace_deadline` de 72 h). O documento detalha o que muda em relação ao
  contrato atual, os pré-requisitos do lado RedGest (que **bloqueiam** a
  migração), o trabalho previsto no PrintGest, as fases de corte (M0–M4) e os
  riscos. `docs/licenciamento_online_first.md` §5/§7 apontam para o plano; nada
  do contrato atual muda enquanto o adapter existir.

### Corrigido

- **Top bar / unidade semeada:** a primeira unidade do bootstrap chamava-se "Filial Matriz" — contraditório (ou a unidade é a matriz, ou é uma filial). Semeia e exibe **"Matriz"**; migração de dados `c4d5e6f7a8b9` (reversível) renomeia a unidade nos bancos já criados; tooltip da top bar explica ("Unidade em uso (matriz ou filial)").
- `PATCH /v1/projetos/cartoes/{id}`: enviar `null` explicitamente agora **limpa** o
  campo (datas, descrição, lembrete) — antes o `null` era ignorado e não havia
  como remover um prazo pela interface.
- Licença: `429` e `5xx` do RedGest deixam de cair em `502 "Resposta inesperada"`
  e passam a ser tratados como indisponibilidade transitória (`503` com backoff,
  `ultimo_erro` registrado) — sem revogar a licença.
- Licença: a recusa reportada dentro de um `200 {valido: false}` (formato previsto
  no manual de integração §8.2) passa a ser tratada — revogação/bloqueio/
  expiração → `423`, chave não reconhecida → `400`, limite → `409` — em vez de
  ser aceita como ativação bem-sucedida.
- Licença: serial digitado sem hífens (ou com espaços/caixa baixa) ia cru para o
  RedGest e voltava `400` de chave inválida, gastando tentativa da cota; agora é
  normalizado para `XXXX-XXXX-XXXX-XXXX` antes do envio e o formato é validado
  **localmente** (`_parse_chave`) — chave truncada responde `400` sem nenhuma
  requisição.

### Alterado

- Licença: o backoff de revalidação passa a 1/5/15/60 min
  (`licenca_backoff_segundos=60,300,900,3600`), saturando no último passo e
  recebendo **jitter** de ±20 % (`licenca_backoff_jitter_percentual`, doc §9.2;
  `0` desliga).

### Alterado

- A antiga `PaginaProjetos` (quadro sobre `/v1/os`, em
  `ui/modulos/os.py`) foi substituída pela nova `ui/modulos/projetos.py`. A
  `PaginaOS`/`PaginaOrcamento` permanecem intactas para os itens internos
  `os`/`orcamento`.
- Tela de **Ativação** deixa de pedir CNPJ + código e passa a pedir apenas a
  **chave de produto** (formatação automática `XXXX-XXXX-XXXX-XXXX`); o diálogo de
  situação mostra chave, plano, estações (limite/em uso) e vigência em vez de
  CNPJ/`token_expira_em`.
- Indicador de licença na tela principal passa a refletir o `estado` (tolerância =
  alerta; revogação/leitura = erro) e se atualiza a cada 5 min; a tela de **Modo
  Leitura** distingue *revogação* de *tolerância esgotada* e mostra a última
  tentativa/erro. Desktop: **247 testes** verdes (+4 xfail, 8 xpass).

### Documentação

- `docs/revisao_projetos_kanban.md`: escopo da Fase 1, decisões tomadas e
  pendências (Fases 2–4).
- `docs/revisao_projetos_fase2.md`: escopo e decisões da Fase 2 (cartão rico:
  etiquetas, checklists, comentários e atividade).
- `docs/plano_resiliencia_licenca.md`: plano das etapas E0–E6 da resiliência da
  licença (E0–E2/E5 **concluídas**; E3/E4 canceladas pelo Contrato C; E6 parcial).
- `docs/licenciamento_online_first.md`: decisões do licenciamento online-first
  vigente (chave de produto, tolerância de 72 h, cadências e estados), o
  algoritmo do `maquina_fingerprint` (§6), o mapa de conformidade com o
  documento de integração do RedGest (§7) e o cofre do SO para a chave (§8).
- `backend/.env.example`: `PRINTGEST_COFRE` e
  `PRINTGEST_LICENCA_BACKOFF_JITTER_PERCENTUAL`.
- `docs/prd_2.0.md` §3: reescrito para o Contrato C (chave de produto validada
  online); tolerância de 72 h, timeout de 90 s com backoff e a regra de que a
  indisponibilidade **não** revoga a licença.

---

## [0.2.2] — 2026-10-16 · `7b9ed50`

### Adicionado

- Camada de movimento (`desktop/printgest/ui/animacao.py`): *springs* aproximados
  por curvas de easing, animações interrompíveis (partem do valor atual),
  materialização por fade e pixmap elevado para arraste. Respeita
  *reduced-motion* e a plataforma `offscreen` (mantém os testes determinísticos).

### Alterado

- **UI adaptada ao Apple Design:** paleta de sistema (janela clara), tipografia
  óptica, cantos contínuos, selos em pílula e estilos para controles que antes
  caíam no visual nativo do Windows (`QMenu`, `QToolTip`, `QCheckBox`,
  `QRadioButton`, `QDialog`/`QMessageBox`).
- Barra lateral colapsa com largura animada; páginas materializam com fade curto.
- Kanban: cartão arrastado vira pixmap com sombra e o *hot spot* respeita onde o
  usuário agarrou; alvo de soltura em tinta de acento.

### Corrigido

- `test_produtos` travava por ordem de inicialização (`_nomes_cat` era lido antes
  de existir durante `super().__init__()`).
- `scripts/setup_postgres.ps1` agora aguarda `pg_isready` antes de consultar o
  banco, em vez de um `sleep` fixo.

### Notas

- Versão do produto alinhada para `0.2.2` no desktop (`__version__`) e no Local
  API Service (`config.version`).

---

## [0.2.1] — 2026-10-11 · `4589597`

- Agendamento: visões Calendário/Lista com CRUD síncrono (mockado em testes);
  `rodar` assíncrono registrado como limitação conhecida (`xfail`).

## [0.2.0] — 2026-10-11 · `6b16140`

- Release 0.2.0: módulos de Projetos (Quadro/Kanban e Lista), Financeiro, Fiscal
  e Configuração.

## [0.1.0] · `e94ae71`

- Primeira versão: base de cadastros (Clientes, Fornecedores, Produtos/Serviços)
  e correções 3.1/3.2.

---

## Correções de histórico de tags

- **2026-10-16 — `v0.2.0` reapontada.** A tag `v0.2.0` estava apontando para o
  commit do refactor de domínio (`e0e7a32`, de 15/10), que é **posterior** ao
  commit da `v0.2.1` (`4589597`, de 11/10) — a ordem cronológica entre as tags
  ficava invertida. A `v0.2.0` foi reapontada para o commit de release real
  (`6b16140`, "Release 0.2.0: Projetos, Financeiro, Fiscal e Configuração") e
  recriada como tag **anotada** (antes era leve), ficando consistente com as
  demais.

  Ordem resultante, verificada por ancestralidade:
  `v0.1.0 < v0.2.0 < v0.2.1 < v0.2.2`.

  > Se você já havia clonado antes desta data, rode
  > `git fetch --tags --force` para descartar a `v0.2.0` antiga localmente.
