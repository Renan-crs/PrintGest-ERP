# Migração para o RedGest v4.x (`/api/v1/licencas/`)

Plano de migração do PrintGest do **Contrato C** (chave de produto, v3.6,
`/api/v1/licencas-software/`) para o **Contrato B** (`Licenca` v4.0,
`/api/v1/licencas/`), que o RedGest aponta como sucessor.

- **Prazo:** o RedGest passou a emitir `Deprecation: true`,
  `Sunset: Mon, 01 Mar 2027` e `Link: .../licencas/; rel="successor-version"` no
  `/licencas-software/`, que **permanece como adapter** até a data. A migração
  deve estar concluída antes de **01/03/2027**.
- **Estado:** planejado — **bloqueado por pré-requisitos do RedGest** (§3). Nada
  do contrato em produção muda enquanto o adapter existir.
- **Referência:** `manual-integracao-sistemas-licenciados.md` §7, §11.4, §12 e
  §14.1; `CHANGELOG-1.0.md` (P2).

## 1. O que muda (Contrato C → Contrato B)

| Eixo | Contrato C (atual) | Contrato B v4.0 (alvo) |
|---|---|---|
| Rota | `POST /api/v1/licencas-software/validar/` | `POST /api/v1/licencas/{uuid}/ativar/` (handshake) + `POST /api/v1/licencas/{uuid}/validar/` |
| Model no RedGest | `LicencaSoftware` | `Licenca` (v4.0) |
| Estratégia | implícita no model | `hardware_bound` (desktop identificado por equipamento) |
| Autenticação | HMAC-SHA256 da `Sistema.api_key` (headers `X-RedGest-*`) | `client_id` + `client_secret` (emitidos no handshake; segredo aparece **uma única vez**) |
| O que o cliente digita | serial `XXXX-XXXX-XXXX-XXXX` | `cnpj` + `codigo_licenca` (o UUID da licença) |
| Resposta de validação | `{valido, expira_em, ativacoes_*}` | `{valida, entitlements, token (JWT RS256), token_expira_em, grace_deadline, modo_leitura, motivo}` |
| Idempotência | não exigida | `Idempotency-Key` (uuid-v4) obrigatória na ativação/validação |
| Fingerprint | SHA-256 canônico do hardware | `hardware_profile` canônico (o RedGest hasheia) — reusar `_fingerprint_do_hardware` |
| Tolerância | `expira_em` + 72 h local | `grace_deadline` do RedGest (72 h em `hardware_bound`) |
| Offline | só até a vigência + 72 h | JWT validável **localmente** (JWK embutida) até o `grace_deadline` |
| Troca de máquina | reativar consome cota | `PUT /licencas/{id}/hardware/` (rebind), limitado por `entitlements.max_rebinds` |
| Revogação | `403 LICENCA_REVOGADA` | `valida=false, motivo=licenca_revogada` |

## 2. Por que não é uma troca de endpoint

`/licencas/` não é um alias do `/licencas-software/`: são **modelos de negócio
diferentes** (manual §1 "Qual rota usar?" e a árvore de decisão da §1).

- `assinatura_simples` tem **grace 0** — adotá-la eliminaria a tolerância de 72 h
  já implementada (o manual §11.2 proíbe explicitamente tolerância local nessa
  estratégia).
- `online_periodic` é para produtos com contratos/entitlements e validação
  central; também serve a um desktop, mas o desenho (conta, webhook de
  `modo_leitura`, TTL de 4 h) é mais pesado do que o PrintGest precisa.
- **`hardware_bound`** é o encaixe natural: desktop instalado, sem conta do
  RedGest, licença por equipamento, fingerprint + rebind e tolerância de 72 h —
  exatamente o que o PrintGest já implementa para o Contrato C.

> **Regra de bolso do manual (§7.1 das rotas):** "se a máquina é identificada e a
  licença é por equipamento → `LICENCA · hardware_bound`". É o nosso caso.

### 2.1 Decisão de produto pendente: a UX de ativação

Hoje o usuário digita **um serial**. No Contrato B a ativação é um *handshake*
com `cnpj` + `codigo_licenca`. Duas saídas:

1. **Dois campos (recomendado):** CNPJ + código, como o manual define. Mantém a
   máscara amigável (`00.000.000/0000-00` e o código copiável).
2. **Um campo:** tratar o serial digitado como o `codigo_licenca`. Exige o
   RedGest emitir o `codigo_licenca` no formato do serial (ou expor um alias) —
   decisão do lado RedGest.

## 3. Pré-requisitos do RedGest (bloqueiam a migração)

- [ ] Onboarding do `printgest` como `LICENCA` + `estrategia_validacao=hardware_bound`
      (**imutável após o primeiro uso** — decidir antes de emitir a 1ª `Licenca`).
- [ ] Schema de `entitlements` (draft-07): `cnpj_vinculado`, `max_estacoes`,
      `max_rebinds`.
- [ ] Chaves JWT (`LICENCE_JWT_PRIVATE_KEY` / `LICENCE_JWT_PUBLIC_KEY`); a
      pública embutida no binário do PrintGest.
- [ ] Emissão de uma `Licenca` para o cliente e entrega de `cnpj` +
      `codigo_licenca`.
- [ ] Endpoint de rebind `PUT /licencas/{id}/hardware/` disponível ao app.
- [ ] Política de *dual-run* (Contrato B convive com o adapter) e confirmação da
      data de sunset.

## 4. Trabalho no PrintGest (fase M2)

- [ ] `licensa_service`: adaptador do Contrato B atrás de
      `PRINTGEST_REDGEST_CONTRATO` (`c` = default atual, `b` = v4.0).
  - [ ] Ativação via handshake com `Idempotency-Key` (uuid4); guardar
        `client_id`/`client_secret` no **cofre do SO** (já existe DPAPI, §8 do
        doc de decisões).
  - [ ] Revalidação com `client_id`/`client_secret` + `hardware_profile`
        canônico (reusar `_fingerprint_do_hardware`, que já ordena chaves).
  - [ ] Persistir `token`/`token_expira_em`/`grace_deadline`; derivar o estado de
        `valida`/`motivo` no lugar de `expira_em` + 72 h.
  - [ ] Verificação **local** do JWT com a JWK embutida → reabilita D3/E3
        (operação offline até o `grace_deadline`).
  - [ ] `motivo=hardware_divergente` → mensagem "rebind necessário" + fluxo de
        rebind.
- [ ] UI de ativação: CNPJ + código (ou alias do serial — §2.1).
- [ ] Migração de instalações: bases do Contrato C **não têm** `client_secret`;
      o corte exige reativação assistida (ou handshake em lote — decidir com o
      RedGest).
- [ ] Testes: os 12 itens da §14.1 do manual viram a matriz de aceite do
      adaptador, exercitada contra o stub local (`scripts/redgest_stub.py`),
      estendido para o Contrato B.

## 5. Fases de corte

| Fase | Conteúdo | Bloqueio |
|---|---|---|
| **M0** (agora) | Observar os headers `Deprecation`/`Sunset`; fechar a UX (§2.1) e pedir o onboarding (§3). Nenhum código de produção muda. | decisão de produto |
| **M1** | RedGest provisiona o modelo v4 do `printgest` e o stub local ganha o Contrato B. | RedGest |
| **M2** | Adaptador Contrato B atrás de flag; *dual-run* com o Contrato C (cada instalação usa um). | M1 |
| **M3** | Piloto em um cliente, medição, virada do default. | M2 |
| **M4** | Remover o Contrato C e a flag (antes de 01/03/2027); atualizar PRD/CHANGELOG. | M3 |

## 6. Riscos

| Risco | Mitigação |
|---|---|
| `tipo_licenciamento`/estratégia imutáveis após o 1º uso | decidir e validar antes de emitir a 1ª `Licenca` do produto |
| Reativação em massa no corte (sem `client_secret` nas bases antigas) | handshake em lote ou reativação assistida no M3 |
| Perda do "serial único" (comercial/UX) | §2.1 — preservar um campo único se o RedGest emitir o código no formato do serial |
| Usar `assinatura_simples` (grace 0) e matar a tolerância de 72 h | **não** usar; o alvo é `hardware_bound` |
| `cryptography` no runtime para validar o JWT | dependência já padrão; se pesar, validar só `exp` no início (risco já mapeado no plano de resiliência §6) |
| Instalações offline por mais de 72 h no contrato novo | `grace_deadline` + política de produto (fade progressivo), não corte duro |

## 7. Referências

- `docs/licenciamento_online_first.md` §5 (depreciação) e §7 (conformidade).
- `docs/plano_resiliencia_licenca.md` (tolerância, backoff, E6).
- RedGest: `manual-integracao-sistemas-licenciados.md` §7 (Contrato B), §11.4
  (`hardware_bound`), §12 (grace), §14.1 (testes obrigatórios);
  `CHANGELOG-1.0.md` (P2 — sunset 01/03/2027).
