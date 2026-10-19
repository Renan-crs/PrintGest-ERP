# Licenciamento online-first do PrintGest (modelo vigente)

Documento de decisão do licenciamento do PrintGest depois da migração para o
**Contrato C** do RedGest (chave de produto validada online). Substitui os
valores do desenho anterior `online_periodic` (JWT de 4 h, tolerância de
24–72 h) e serve de referência para `docs/prd_2.0.md` §3 e
`docs/plano_resiliencia_licenca.md`.

## 1. Modelo

- **Chave de produto** no formato `XXXX-XXXX-XXXX-XXXX` (16 hexadecimais em 4
  blocos), digitada pelo usuário na 1ª execução — modelo mental de
  CorelDRAW/Windows.
- **Validação online** em `POST {redgest}/api/v1/licencas-software/validar/`,
  autenticada por **HMAC-SHA256** do `Sistema.api_key`:
  `X-RedGest-Signature: sha256=<hex(hmac(segredo, utf8(nonce+timestamp) + body))>`,
  `X-RedGest-Nonce`, `X-RedGest-Timestamp` (ISO-8601 UTC, janela de 300 s).
- **Sem JWT.** A resposta traz `valido`, `expira_em` (`null` = vitalícia),
  `primeira_ativacao`, `ativacoes_realizadas` e `limite_ativacoes`.
- **Fingerprint da máquina** (`maquina_fingerprint`, SHA-256) identifica a
  instalação; reativar a mesma máquina não consome o `limite_ativacoes`.

Só o Local API Service fala com o RedGest; as estações-cliente nunca o fazem.

## 2. Cadências e janelas (defaults)

| Parâmetro | Default | Papel |
|---|---|---|
| `licenca_refresh_intervalo_segundos` | 300 s | De quanto em quanto tempo o loop acorda. |
| `licenca_revalidar_a_cada_segundos` | 6 h | De quanto em quanto tempo o RedGest é consultado de fato. |
| `licenca_timeout_segundos` | 90 s | Timeout da chamada (Render frio responde em 30–60 s). |
| `licenca_tolerancia_horas` | 72 h | Operação normal após `expira_em` vencer, sem contato com o RedGest. |
| `licenca_backoff_segundos` | 60/300/900 s | Recuo progressivo após falhas; satura em 15 min e zera no sucesso. |

## 3. Estados derivados (nunca persistidos como verdade)

- `ativa` — `status=ativa` e `expira_em` no futuro (ou vitalícia).
- `tolerancia` — `expira_em` vencido, dentro de `tolerancia_expira_em`; ainda
  **escreve**, com aviso ao usuário.
- `leitura` — tolerância esgotada, ou `status` local `bloqueada`/`expirada`.
- `revogada` — `status=revogada` (leitura imediata, sem tolerância).
- `nao_ativada` — não há linha local.

`modo_leitura = estado in {leitura, revogada, nao_ativada}`.

## 4. Resiliência (por que a indisponibilidade não bloqueia)

- `httpx.HTTPError` (timeout/DNS/5xx) → **503** e **nunca** revoga; a licença
  segue válida até `expira_em`.
- Sem `redgest_api_key` configurada a ativação responde **502** antes de
  qualquer chamada de rede.
- Revogação/bloqueio/expiração só vêm de resposta explícita do RedGest
  (`403 LICENCA_REVOGADA`/`LICENCA_BLOQUEADA`/`LICENCA_EXPIRADA`).
- Enquanto o RedGest estiver fora, o sistema continua operando dentro da
  vigência + 72 h de tolerância.

## 5. Depreciação

O manual do RedGest marca `/licencas-software/` (v3.6) como depreciado em favor
de `/api/v1/licencas/` (v4.x, assertion/JWK), com *sunset* em **01/03/2027**.
O PrintGest deverá migrar antes dessa data.
