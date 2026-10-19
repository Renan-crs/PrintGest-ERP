# Plano — Resiliência da licença do PrintGest (RedGest indisponível)

Plano de implementação derivado do documento
`Disponibilidade do PrintGest com o RedGest em planos gratuitos.md`
(18/10/2026). Cobre **apenas o lado PrintGest** — o que o ERP precisa fazer para
sobreviver ao RedGest fora do ar. O que é responsabilidade do RedGest (§3 e §4
daquele documento) está listado em *Fora de escopo*.

Referências de linha do código de hoje estão em
`backend/app/services/licensa_service.py`, `backend/app/core/config.py`,
`backend/app/models/licenca.py`, `desktop/printgest/main.py`,
`desktop/printgest/ui/modoleitura.py` e `desktop/printgest/ui/tela_principal.py`.

> **Revisão 2.1.0 — Contrato C (chave de produto).** O licenciamento migrou do
> modelo `online_periodic` (CNPJ + código → JWT) para o **Contrato C** do RedGest
> (`/api/v1/licencas-software/validar/`): chave de produto `XXXX-XXXX-XXXX-XXXX`
> validada online, **sem JWT**. Consequências para este plano:
>
> - **D3 e E3 (validação local do JWT)**: cancelados — não há JWT a verificar.
> - **D4 e E4 (extensão de emergência assinada)**: cancelados — a tolerância de
>   72 h cobre a indisponibilidade.
> - **D1, D2, D5, E0, E1, E2, E5 e E6** seguem válidos; onde o texto abaixo falar
>   em "token"/`token_expira_em`, leia-se a vigência local `expira_em`.
> - A cadência "renova antes de 1 h" (`licenca_renova_antes_segundos`) foi
>   substituída por `licenca_revalidar_a_cada_segundos` (default 6 h).
> - Decisões e contrato vivos em `docs/licenciamento_online_first.md`; o PRD
>   (`docs/prd_2.0.md` §3) foi reescrito para o Contrato C.

---

## 0. Objetivo e critério de sucesso

**Objetivo.** Fazer o PrintGest continuar operando (inclusive escrevendo e
emitindo fiscal) enquanto o RedGest estiver inacessível, distinguindo
*indisponibilidade* de *revogação*, e avisando o usuário com a mensagem correta.

**Critério de sucesso (testes de aceite §5 do documento):**

1. RedGest frio (resposta em ~60 s): a renovação conclui sem erro visível.
2. RedGest inacessível por até ~72 h após o token expirar: opera normalmente.
3. Queda de ~5 dias (72 h de token + 72 h de tolerância): nenhum cliente perde
   acesso.
4. Resposta explícita de revogação: modo leitura dentro da janela de renovação.
5. Em qualquer caso, a mensagem ao usuário diz *qual* é o motivo.

---

## 1. Linha de base (o que existe hoje)

| Ponto | Hoje | Arquivo |
| --- | --- | --- |
| Renovação em background | Existe (`loop_renovacao` no lifespan, em thread) | `licensa_service.py:289`; `main.py:83` |
| Timeout para o RedGest | **10 s** | `licensa_service.py:53` |
| Cadência | Loop a cada 300 s; renova quando falta ≤ 3600 s; retry fixo, sem backoff | `config.py:24-25`; `licensa_service.py:279` |
| Revogação | Só 401/403 marca `revogada` | `licensa_service.py:239-249` |
| Tolerância pós-expiração | **Não existe** — vira modo leitura na hora | `licensa_service.py:98-105` |
| Validação local do JWT | Não existe (confia só em `token_expira_em`) | `licenca.py` (sem verificação) |
| Extensão de emergência | Não existe | — |
| Estados expostos | Só `modo_leitura` (bool) | `licensa_service.py:108-134` |
| Erro de rede na renovação manual | Vira **HTTP 500** cru | `licensa_service.py:234-250` |
| Ritmo da UI | Status lido **uma vez** no login (timer single-shot) | `tela_principal.py:571-575` |

---

## 2. Decisões (defaults a implementar; revisar depois)

| # | Decisão | Default proposto | Observação |
| --- | --- | --- | --- |
| D1 | Duração da tolerância pós-expiração | **72 h** | É o número já anunciado na UI (`ativacao.py:224`). |
| D2 | Backoff de tentativas | **1 / 5 / 15 / 60 min** com **jitter ±20 %**, saturando no último passo; zera no sucesso | Doc de integração §9.2: `licenca_backoff_segundos` + `licenca_backoff_jitter_percentual`. O `±` espalha as instalações que caíram juntas (manada). |
| D3 | Validação local do token (assinatura RS256) | **Descartado** (Contrato C: sem JWT) | Não reverte mais §3.3 do PRD; ver revisão 2.1.0. |
| D4 | Extensão de emergência assinada | **Descartado** (Contrato C) | A tolerância de 72 h cobre a indisponibilidade; ver revisão 2.1.0. |
| D5 | Cadência de renovação quando o token é longo | Manter checagem a cada 5 min, renovando só na janela (`renova_antes`) | O "a cada 6 h" do documento é propriedade do TTL do RedGest. |

> D3 e D4 **reabrem** itens removidos de propósito no `docs/prd_2.0.md` §3.3
> (ativação offline assistida, cache/HMAC). Se forem adiante, o PRD precisa ser
> atualizado explicitamente para não ficar contraditório.

---

## 3. Etapas

### E0 — Configuração central ✅
- [x] `core/config.py`: `licenca_timeout_segundos: int = 90`.
- [x] `core/config.py`: `licenca_tolerancia_horas: int = 72`.
- [x] `core/config.py`: backoff — `licenca_backoff_segundos: str = "60,300,900,3600"`
      (string + propriedade `settings.licenca_backoff -> list[int]`;
      pydantic-settings não parseia `list[int]` de env de forma confiável).
- [x] `core/config.py`: jitter do backoff —
      `licenca_backoff_jitter_percentual: int = 20` (doc §9.2).
- [x] `core/config.py`: cofre do SO — `cofre: str = "dpapi"` (doc §9.4).
- [x] `backend/.env.example`: documentar as novas variáveis.
- [ ] Revisar `licenca_renova_antes_segundos` (hoje 1 h) para a nova realidade.
      *Mantido em 3600 s (D5): é a cadência de checagem (5 min) que controla.*

**Aceite:** `settings` carrega os defaults; testes existentes seguem verdes.

### E1 — Resiliência de rede ✅
- [x] `_cliente()` usa `settings.licenca_timeout_segundos` no lugar de `10.0`.
- [x] `ativar()` e `renovar()`: encapsular a chamada HTTP em `try/except
      httpx.HTTPError` e traduzir para `HTTPException(503, "Não foi possível
      falar com o servidor de licenças …")` (`_indisponivel`). Nunca sobe 500 cru.
- [x] `loop_renovacao`/`_tentativa_renovacao`: contador de falhas consecutivas
      com backoff (D2: 1/5/15/60 min, saturando no último); zera no sucesso; nunca
      marca `revogada` por timeout/5xx/429/DNS.
- [x] Registrar em log a causa da falha. *(Sem `request_id`: o logger do daemon
      já inclui contexto; adicionar se a observabilidade pedir.)*

**Aceite:** transporte simulado que demora > 90 s ou estoura timeout → a
tentativa falha sem marcar revogação e sem derrubar o loop; a próxima tentativa
respeita o backoff.

### E2 — Máquina de estados e tolerância ✅
- [x] `models/licenca.py`: `tolerancia_expira_em`, `ultima_tentativa_em`,
      `ultimo_erro` (nullable) + `ultimo_erro` preenchido em falha/revogação.
- [x] Migração Alembic **reversível** (aditiva), novo head `c9e4f1a7b2d8`
      (up/down/up validados no Postgres).
- [x] `licensa_service`: estados `ativa` / `tolerancia` / `leitura` /
      `revogada` (`nao_ativada` quando não há linha local):
  - `ativa` — `status=ativa` e `token_expira_em > agora`;
  - `tolerancia` — `status=ativa` e `token_expira_em <= agora <=
    tolerancia_expira_em`;
  - `leitura` — tolerância esgotada;
  - `revogada` — `status=revogada` (leitura imediata, sem tolerância).
- [x] `_recalcular_estado`: `modo_leitura = estado in {leitura, revogada}` (e
      `nao_ativada`).
- [x] Em `renovar()` bem-sucedido: `tolerancia_expira_em = token_expira_em +
      tolerancia`. Idem em `ativar()`.
- [x] `situacao()`: devolver `estado`, `motivo`, `tolerancia_expira_em`,
      `ultima_tentativa_em`, `ultimo_erro`, além do que já devolve.


**Aceite:** token expirado dentro da tolerância → `modo_leitura=False`,
`estado="tolerancia"`, escritas liberadas (sem 423); após a tolerância →
`estado="leitura"` e 423 nas escritas.

### E3 — Validação local do token (D3) — ❌ cancelada (Contrato C)
- [ ] Adicionar `cryptography` ao `backend/requirements.txt` (justificativa:
      verificar a assinatura RS256 offline).
- [ ] Chave pública do RedGest configurável (`PRINTGEST_REDGEST_PUBKEY` ou
      arquivo); validar assinatura + `exp` do JWT contra o relógio local.
- [ ] Política: assinatura inválida → `estado="leitura"` com
      `motivo="licença inválida"` (tamper), distinta de indisponibilidade.
- [ ] Documentar a limitação de relógio local (rollback estende uso) — herdar a
      decisão do PRD v2.0 §3.3 ou assumir o risco explicitamente.

**Aceite:** JWT adulterado → leitura; JWT válido sem rede → `ativa`/`tolerancia`.

### E4 — Extensão de emergência (D4) — ❌ cancelada (Contrato C)
- [ ] Formato: JSON `{cnpj, emitido_em, valido_ate}` + assinatura RSA
      (destacada), assinado por chave privada mantida **offline** pelo dono.
- [ ] Serviço para importar/validar o arquivo com a chave pública embutida;
      estende `tolerancia_expira_em` até `valido_ate` (nunca reduz).
- [ ] Tela de importação (admin) no desktop.
- [ ] Registrar a extensão em log/atividade.

**Aceite:** arquivo válido estende a tolerância; arquivo inválido/CNPJ diferente
é recusado com mensagem clara.

### E5 — UI (desktop) — concluído
- [x] `modoleitura.py`: mensagem honesta por estado — revogação (sem tolerância)
      × tolerância expirada; inclui "Última tentativa: <data/hora>" e
      "Último erro: …" no diagnóstico (`situacao` passado por `main.py`).
- [x] `tela_principal.py`: `QTimer` repetitivo (5 min) repintando o indicador;
      `_texto_licenca`/`_estilo_licenca`/`_detalhe_texto` por `estado`
      (tolerância = alerta, não erro).
- [x] `main.py`: passa a `situacao` completa para a tela de modo leitura.
- [x] `ativacao.py`: já anunciava "Tolerância Offline: 72 Horas" — alinhado.
- [x] Banner **progressivo** em `estado="tolerancia"` (doc de integração §9.3):
      mensagem "Sem conexão com o servidor de licenças. O PrintGest continuará
      funcionando normalmente até DD/MM/AAAA HH:MM", tempo restante recomposto a
      cada minuto (`QTimer`, sem rede) e barra com a fração da tolerância ainda
      disponível (`fracao_tolerancia`). Não bloqueia escrita alguma e sai de cena
      sozinho quando a revalidação volta a `ativa`.

**Aceite:** testes de UI mostram a mensagem de revogação (✅), o diagnóstico de
tolerância (✅) e o banner progressivo com prazo + tempo restante + barra, além
de a mudança de estado (`tolerancia` → `ativa`) retirar o banner sem reabrir a
tela (✅).

### E6 — Testes — concluído
- [x] `backend/tests/test_licenciamento.py` (via `httpx.MockTransport`): timeout
      na ativação/renovação (503, sem revogação), janela de tolerância,
      tolerância esgotada → leitura, diagnóstico da falha, backoff (1/5/15/60),
      `429`/`5xx` → 503, recusa em `200 {valido: false}` e fingerprint canônico.
- [x] `desktop/tests/test_modoleitura.py` e `test_tela_principal.py`: mensagem
      por estado (revogada × tolerância) e texto/estilo do indicador.
- [x] Cold start com *delay* real (`_RedGestReal`, socket local que dorme antes
      de responder): `test_cold_start_lento_conclui_sem_erro_visivel` (lento,
      mas dentro do timeout → 200 sem erro) e
      `test_cold_start_estoura_timeout_real_e_recupera` (acima do timeout →
      503 sem revogar e recuperação quando o RedGest responde). O
      `MockTransport` do httpx **não** aplica timeout ao handler; só um
      transporte real prova que `licenca_timeout_segundos` está ligado à
      requisição. O atraso de 60 s do cenário vira 1,5 s contra timeout de
      0,2 s (mesma relação, sem prender a suíte).
- [x] Rollover — o Contrato C **não tem token** (D3/D4 cancelados): o
      equivalente é a vigência.
      `test_revalidacao_renova_a_vigencia_e_reativa` (revalidar em tolerância
      com `expira_em` novo substitui o local e volta a `ativa`, recalculando a
      tolerância) e `test_revalidacao_de_licenca_vitalicia_continua_vitalicia`
      (`expira_em: null` permanece vitalícia).
- [x] Cada teste de aceite da §0 mapeado a um teste nomeado:

| Aceite (§0) | Teste nomeado |
| --- | --- |
| 1. RedGest frio (~60 s): a renovação conclui sem erro visível | `test_cold_start_lento_conclui_sem_erro_visivel` (backend) |
| 2. Inacessível por até 72 h após a vigência: opera normalmente | `test_vigencia_vencida_dentro_da_tolerancia_opera_normal` (backend); `test_banner_tolerancia_aparece_com_prazo_e_restante` (desktop) |
| 3. Queda longa: nenhum cliente perde acesso | `test_cold_start_estoura_timeout_real_e_recupera`, `test_429_vira_503_e_nao_revoga` e `test_erro_5xx_vira_503_e_registra_diagnostico` (indisponibilidade nunca revoga); `test_revalidacao_renova_a_vigencia_e_reativa` (retorno) |
| 4. Revogação explícita: modo leitura dentro da janela | `test_revogacao_volta_ao_modo_leitura` e `test_recusa_200_revogada_entra_modo_leitura` (backend) |
| 5. A mensagem ao usuário diz *qual* é o motivo | `test_tolerancia_esgotada_mostra_diagnostico`, `test_revogada_mostra_mensagem_de_revogacao`, `test_mensagem_tolerancia_traz_o_prazo_do_documento` |

**Nota (Contrato C).** Os aceites 1–2 falavam em *token* porque o plano original
previa JWT local (D3/D4); com o Contrato C a vigência (`expira_em`) faz o papel
do token e a tolerância de 72 h cobre o vencimento. O aceite 3 ("72 h de token +
72 h de tolerância") vira "vigência + 72 h": uma queda de vários dias não bloqueia
enquanto a vigência local valer, e nenhuma falha de rede revoga a licença.

---

## 4. Fora de escopo (é do RedGest)

- Endpoint `/health` que consulta o Supabase e o pinger externo (UptimeRobot /
  cron-job.org / GitHub Actions).
- Limite de 750 h/mês do Render e alertas de indisponibilidade.
- Backup agendado (`pg_dump`) do banco de licenças.
- Migração para planos pagos (§4: Render Starter + Supabase Pro). **Entrada para
  o preço da licença.**

---

## 5. Impacto em documentos

- [x] `docs/prd_2.0.md` §3.2: tolerância 72 h (`licenca_tolerancia_horas`),
      timeout 90 s com backoff 60/300/900/3600 s e a regra de que indisponibilidade
      **não** revoga (item novo, nº 8).
- [x] `docs/prd_2.0.md` §3: reescrito para o Contrato C (chave de produto +
      validação online), com a nota de que D3/D4 não se aplicam.
- [x] `docs/licenciamento_online_first.md`: documento criado com as decisões
      online-first vigentes (Contrato C, tolerância de 72 h, cadências).
- [x] `CHANGELOG.md` (`## [Não lançado]`).

---

## 6. Riscos

| Risco | Mitigação |
| --- | --- |
| Timeout de 90 s prende o worker thread | O loop já roda em `asyncio.to_thread`; manter timeout só na chamada ao RedGest, nunca nas rotas locais. |
| Rollback de relógio local estende uso | Assumido conforme PRD v2.0 §3.3 (ou tratar em D3). |
| `cryptography` no runtime | Dependência pesada, porém padrão; alternativa é validar só `exp` no início. **Decidir.** |
| D4 reintroduz fluxo offline | Manter a chave privada offline e a importação auditável. |
| Confusão com o PRD | Atualizar o PRD na mesma entrega que reverter §3.3. |

---

## 7. Ordem recomendada

1. **E0 + E1 + E2** — resolve o cenário que o documento quer cobrir (o "mínimo
   vendável" da resiliência). Entregável já utilizável.
2. **E5 + E6** — UI e testes. **E5 e E6 concluídos**: o banner progressivo de
   tolerância (§9.3) e a suíte de aceite nomeada (cold start real, rollover da
   vigência e o mapa dos 5 aceites da §0).
- ~~E3 e E4~~ cancelados: o Contrato C não emite JWT (ver revisão 2.1.0).
- E0..E2 destravam os testes de aceite 1–4; o aceite 5 depende de E5.

**Sugestão de versão:** `0.3.0` (junto com o restante do `Não lançado`).
