# Changelog

Histórico de versões do **PrintGest ERP**. Formato inspirado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e versionamento
semântico.

As versões correspondem a tags anotadas neste repositório; o commit de destino
de cada tag está indicado para rastreabilidade.

---

## [Não lançado]

### Adicionado

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
- **Licença resiliente à indisponibilidade do RedGest.** Erro de rede na
  ativação/renovação agora vira `503` (antes `500`); timeout de contato
  configurável (`licenca_timeout_segundos`, 90 s) e backoff progressivo no loop
  (`licenca_backoff_segundos`, 60/300/900 s). A licença ganha estados derivados
  (`ativa`/`tolerancia`/`leitura`/`revogada`/`nao_ativada`) e janela de tolerância
  offline de 72 h (`licenca_tolerancia_horas`), contada da expiração do token:
  enquanto o RedGest estiver fora, o sistema **continua escrevendo**.
- Migração `c9e4f1a7b2d8` (aditiva e reversível) guarda a tolerância e o
  diagnóstico (`ultima_tentativa_em`/`ultimo_erro`), exposto em `GET /v1/licenca`.
- 5 testes novos de resiliência em `backend/tests/test_licenciamento.py` (timeout
  → 503 sem revogar, janela de tolerância, transição para leitura, diagnóstico e
  base legada), 15 no arquivo. Backend: **150 testes** verdes.

### Corrigido

- `PATCH /v1/projetos/cartoes/{id}`: enviar `null` explicitamente agora **limpa** o
  campo (datas, descrição, lembrete) — antes o `null` era ignorado e não havia
  como remover um prazo pela interface.

### Alterado

- A antiga `PaginaProjetos` (quadro sobre `/v1/os`, em
  `ui/modulos/os.py`) foi substituída pela nova `ui/modulos/projetos.py`. A
  `PaginaOS`/`PaginaOrcamento` permanecem intactas para os itens internos
  `os`/`orcamento`.
- Indicador de licença na tela principal passa a refletir o `estado` (tolerância =
  alerta; revogação/leitura = erro) e se atualiza a cada 5 min; a tela de **Modo
  Leitura** distingue *revogação* de *tolerância esgotada* e mostra a última
  tentativa/erro. Desktop: **245 testes** verdes.

### Documentação

- `docs/revisao_projetos_kanban.md`: escopo da Fase 1, decisões tomadas e
  pendências (Fases 2–4).
- `docs/plano_resiliencia_licenca.md`: plano das etapas E0–E6 da resiliência da
  licença (E0–E2/E5 concluídas; E3/E4 e o banner progressivo em aberto).
- `docs/prd_2.0.md` §3.2: tolerância de 72 h, timeout de 90 s com backoff e a
  regra de que a indisponibilidade **não** revoga a licença.

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
