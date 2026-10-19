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
  instalação; reativar a mesma máquina não consome o `limite_ativacoes`. É
  calculado a partir de identificadores **estáveis** de hardware (ver §6).

Só o Local API Service fala com o RedGest; as estações-cliente nunca o fazem.

## 2. Cadências e janelas (defaults)

| Parâmetro | Default | Papel |
|---|---|---|
| `licenca_refresh_intervalo_segundos` | 300 s | De quanto em quanto tempo o loop acorda. |
| `licenca_revalidar_a_cada_segundos` | 6 h | De quanto em quanto tempo o RedGest é consultado de fato. |
| `licenca_timeout_segundos` | 90 s | Timeout da chamada (Render frio responde em 30–60 s). |
| `licenca_tolerancia_horas` | 72 h | Operação normal após `expira_em` vencer, sem contato com o RedGest. |
| `licenca_backoff_segundos` | 60/300/900/3600 s | Recuo progressivo após falhas (1/5/15/60 min); satura no último passo e zera no sucesso. |

## 3. Estados derivados (nunca persistidos como verdade)

- `ativa` — `status=ativa` e `expira_em` no futuro (ou vitalícia).
- `tolerancia` — `expira_em` vencido, dentro de `tolerancia_expira_em`; ainda
  **escreve**, com aviso ao usuário.
- `leitura` — tolerância esgotada, ou `status` local `bloqueada`/`expirada`.
- `revogada` — `status=revogada` (leitura imediata, sem tolerância).
- `nao_ativada` — não há linha local.

`modo_leitura = estado in {leitura, revogada, nao_ativada}`.

## 4. Resiliência (por que a indisponibilidade não bloqueia)

- `httpx.HTTPError` (timeout/DNS) e **5xx/429** do RedGest → **503** e **nunca**
  revogam; a licença segue válida até `expira_em` e o loop respeita o backoff.
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

## 6. Fingerprint da máquina (doc de integração RedGest §7)

`maquina_fingerprint` é o SHA-256 (hex minúsculo) do JSON **canônico** — chaves
ordenadas, sem espaços — de identificadores **estáveis** de hardware lidos via
CIM/PowerShell:

| Campo | Origem |
|---|---|
| `bios_uuid` | `Win32_ComputerSystemProduct.UUID` |
| `placa_mae_serial` | `Win32_BaseBoard.SerialNumber` |
| `cpu_id` | `Win32_Processor.ProcessorId` |
| `disco_serial` | `Win32_DiskDrive.SerialNumber` (disco de índice 0) |

Regras (doc §7.1/§7.2): **não** usar hostname, usuário, IP, MAC, volume ou data
de instalação (mudam); campos ausentes são **omitidos** (nunca `null`);
preenchimentos genéricos (`None`, `To Be Filled By O.E.M.`, tudo zeros) são
descartados. Assim o mesmo computador mantém o fingerprint após reinstalar o
PrintGest e não consome cota extra de ativação. Sem hardware legível, o
fingerprint cai para `arquitetura` + `processador` (ainda estável). O valor do
`maquina_fingerprint` pode ser fixado por `PRINTGEST_MAQUINA_FINGERPRINT` (VMs
sem SMBIOS confiável, testes ou suporte).

## 7. Conformidade com a documentação oficial do RedGest

Referência: *"Documento de Integração — chave de ativação (serial)"* v1.0
(18/10/2026), aprovado para implementação. Pontos conferidos no código:

| Item da doc | Situação |
|---|---|
| §4 endpoint `POST /api/v1/licencas-software/validar/` | ✅ `CAMINHO_VALIDAR` |
| §5.1 `X-RedGest-Nonce` (Base64 de 32 bytes, único por requisição) | ✅ `os.urandom(32)` → base64 |
| §5.1 `X-RedGest-Timestamp` (`YYYY-MM-DDTHH:MM:SSZ`, UTC) | ✅ `strftime` com `Z` |
| §5.2 `sha256=` + HMAC-SHA256(segredo, utf8(nonce+timestamp)+corpo) | ✅ `_assinatura` (corpo = bytes exatos enviados) |
| §5.3 janela de 300 s | ✅ relógio do SO; tolerância é do servidor |
| §7 fingerprint estável + JSON canônico + SHA-256 | ✅ §6 acima |
| §8.3 403 `LICENCA_REVOGADA`/`_BLOQUEADA`/`_EXPIRADA` → leitura | ✅ 423 local + estado `revogada`/`leitura` |
| §8.3 409 `LIMITE_ATIVACOES_EXCEDIDO` | ✅ 409 |
| §8.3 401 (assinatura) | ✅ 502 (erro de integração, não do usuário) |
| §8.2 recusa em `200 {valido: false}` | ✅ tratada (`_tratar_recusa`) |
| §8.3 429 | ✅ 503 + backoff, sem revogar |
| §9.1 timeout 90 s; renovação a cada 6 h; tolerância 72 h; rede não revoga | ✅ |
| §9.2 backoff 1/5/15/60 min | ✅ `licenca_backoff_segundos` |

Divergências assumidas:

- **§9.2 jitter**: o backoff não adiciona jitter (é uma instalação por cliente,
  não há *thundering herd* contra o RedGest).
- **§9.4 cofre do SO**: a chave fica na tabela local `licenca` (Postgres do Local
  API Service), não em DPAPI/Keychain. O Local API Service é a fronteira de
  confiança e precisa da chave para revalidar; cifrar em repouso exigiria uma
  segunda credencial local, sem ganho real de segurança no modelo atual.
- **§10 migração v4.x**: o `/licencas-software/` é depreciado (sunset
  01/03/2027) — ver §5.
