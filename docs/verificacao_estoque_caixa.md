# Verificação das chamadas API ↔ endpoints — Estoque e Caixa/Financeiro

Verificado em 19/11/2026.

## Contrato conferido — paths e chaves consistentes

Todos os métodos usados pelas telas têm rota correspondente em
`app.main.app.routes`, com payloads idênticos aos schemas:

- `GET /v1/estoque`, `/resumo`, `/reposicao`, `/{id}/kardex`;
  `POST /v1/estoque/movimentar`;
  `GET/POST /v1/estoque/transferencias`, `.../{id}/receber`, `.../{id}/cancelar`.
- `GET /v1/financeiro/caixa/atual`, `POST .../abrir`, `.../{id}/movimento`,
  `.../{id}/fechar`, `GET .../{id}/extrato`;
  `GET/POST /v1/financeiro/contas-{receber|pagar}` e `/.../{id}/baixa`.

Chaves conferem: `motivo`, `quantidade`, `produto_id`, `filial_destino_id`,
`valor_abertura`, `valor_informado`, `valor_pago`, `data_pagamento`,
`status_conta`. Ajuste sem motivo é barrado na UI **e** no schema/service;
a transferência só soma estoque no destino após confirmação; o fechamento de
caixa recalcula a mesma diferença da UI. Nenhuma rota inexistente.

## Bugs encontrados e corrigidos

| # | Severidade | Achado | Correção |
|---|---|---|---|
| 1 | 🔴 | **Tela de Transferências quebrava ao abrir**: `em_volta`, `estado_primario` e `estado_secundario` eram usados mas não importados (`NameError`). Nenhuma das 4 operações era alcançável. | Imports adicionados; teste de instanciação da tela. |
| 2 | 🔴 | **`Api.listar_transferencias()` devolvia só a lista**, mas a tela esperava `{"data": ...}` — grade sempre vazia. | Método agora normaliza o envelope (`data`/`total`/`limit`/`offset`). |
| 3 | 🟠 | **RBAC Operador → Caixa**: `pode_abrir("operador","caixa")` era `True` (rank hierárquico), mas o backend usa `require_perfis(CAIXA, GERENTE, ADMIN)` e responde 403. | Item `caixa` passou a declarar `niveis` explícitos; `pode_abrir` respeita listas não hierárquicas. |
| 4 | 🟠 | **Kardex de transferência com saldos trocados**: `saldo_anterior` era lido **depois** do UPDATE (saída de 3 de 10 virava 7→4 em vez de 10→7). | Leitura do saldo antes da atualização; teste cobre saída e entrada. |
| 5 | 🟡 | Status HTTP 409/401/423 descartados em Estoque/Caixa (callbacks de 1 argumento). | Callbacks de escrita/leitura aceitam status; 409 de estoque e caixa mostram o `detail` do servidor; 401/423 avisam sem limpar sessão. |
| 6 | 🟡 | Erro do resumo de estoque era silencioso (`on_erro=lambda msg: None`), KPIs ficavam em "—". | Aviso ao operador e KPIs zerados. |
| 7 | 🟡 | Payload de transferência usava `CampoTexto` para quantidade (`"2,5"` → 422), sem validação e sem trava de duplo POST. | `CampoValor`, validação de IDs/quantidade, botão travado durante a request. |
| 8 | 🔵 | Colunas `produto_nome`/`destino` não existem em `TransferenciaOut` (sempre "—"); estado cru. | Colunas trocadas por `produto_id`/`filial_destino_id`; rótulos de estado. |
| 9 | 🔵 | `meta.total` de transferências era o tamanho da página — paginação nunca avançava. | `transferencia_service.contar()` com `count()` real. |

## Ressalvas

- `registrar_saida` usa `UPDATE ... WHERE saldo >= qtd` (atômico) e o serviço
  de movimentação manual usa `SELECT ... FOR UPDATE` + checagem — ambas seguras
  contra concorrência, apenas estratégias diferentes.
- A filial do destino continua implícita no escopo do usuário (sem seletor de
  filial na tela); para transferir é preciso um usuário da filial de destino
  confirmar o recebimento, conforme PRD §5.6.

## Validação

- Backend: **409 passed** (2 novos: kardex e paginação de transferências).
- Desktop: **440 passed, 4 xfailed** (4 novos: tela de transferências,
  validação/payload, status e RBAC de Caixa).
- Neon: head Alembic `a0b1c2d3e4f5` — nenhuma migration nova.
