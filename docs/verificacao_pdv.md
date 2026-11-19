# Verificação das chamadas API ↔ endpoints — PDV (Venda Balcão)

Verificado em 19/11/2026.

## Divergências encontradas e corrigidas

| # | Divergência | Correção |
|---|---|---|
| 1 | O PDV exige CAIXA (`/v1/vendas` → `require_nivel(CAIXA)`), mas carregava catálogos em `/v1/clientes`, `/v1/produtos`, `/v1/funcionarios` (OPERADOR) e `/v1/usuarios` (ADMIN). Um CAIXA exclusivo recebia 403 silencioso e via combos/grade vazios. | Novo router **`/v1/pdv/*`** (`app/api/pdv.py`), somente GET, com `require_nivel(CAIXA)` — hierárquico, legível por todos os níveis. |
| 2 | `limit=1000` do PDV era limitado a 200 pela fábrica de CRUD (`crud_factory.py`). | Os endpoints `/v1/pdv/{clientes,produtos,funcionarios}` usam teto de 5000 e devolvem o catálogo inteiro. |
| 3 | O filtro de operadores do Histórico chamava `/v1/usuarios` (ADMIN) e expunha `UsuarioOut` completo a quem pudesse chamá-lo. | `/v1/pdv/operadores` devolve apenas `id`, `nome`, `login` (projeção `OperadorOut`). |
| 4 | Todo 409 era apresentado como "Estoque insuficiente", inclusive "Caixa fechado — abra o caixa antes de registrar vendas." | `_erro_salvar` usa o `detail` do servidor; título "Caixa fechado" quando aplicável, "Conflito ao finalizar" nos demais. |
| 5 | "Limpar filtros" chamava `_aplicar_filtro("ok")` e deixava o histórico preso em "Finalizadas" (além de duplicar a requisição). Agora volta para "Todas" com uma única recarga. Também havia chamada a `CampoBusca.definir()`, método inexistente — o botão quebrava. | `_limpar_filtros_historico` ajustado; `CampoBusca.definir()` implementado sem disparar debounce. |
| 6 | `documento_fiscal_id` era gravado pelo backend na emissão da NFC-e, mas a coluna Fiscal do PDV mostrava sempre "—". | Coluna e detalhe da venda exibem `NFC-e #<id>`; lista recarrega após emissão. |
| 7 | 401/423 durante o uso do PDV não tinham tratamento (a maioria dos `on_erro` não aceitava o `status_code` preservado por `tarefas.py`). | Callbacks de operações sensíveis aceitam status; `_erro_sessao` avisa 401 (sessão encerrada) e 423 (modo leitura) **sem limpar a sessão**. |
| 8 | Resumo da página e resumo consolidado (assíncrono) escreviam no mesmo `_lbl_resumo_hist`. | Rótulo próprio `_lbl_resumo_consolidado`. |
| 9 | `catalogos.invalidar("vendas")` no `_salvo` não tinha efeito (a lista usa `tarefas.rodar` direto). | Removido; o refresh real já é `self.recarregar(...)`, feito logo em seguida. |

## Contrato conferido (consistente)

- `GET /v1/vendas` — `status_venda`, `forma_pagamento`, `operador_id`, `data_inicio`,
  `data_fim`, `q`, `limit`, `offset` — bate com `Api.listar_vendas`.
- `GET /v1/vendas/resumo` — mesmos filtros; bate com `Api.resumo_vendas`.
- `POST /v1/vendas` — 409 "Caixa fechado" (`balcao.py`) e 409 de estoque
  (`venda_service.py`, `UPDATE ... WHERE saldo >= qtd`).
- `DELETE /v1/vendas/{id}` — motivo de cancelamento em `VendaCancelIn`.
- `GET /v1/financeiro/caixa/atual`, `POST .../abrir` — `require_perfis(CAIXA, GERENTE, ADMIN)`.
- `POST /v1/fiscal/documentos/emitir` — mesmo RBAC; `VendaOut.documento_fiscal_id`
  preenchido pelo `fiscal_service`.
- Nenhuma rota inexistente, nenhuma chave de resposta divergente.

## RBAC preservado

As rotas originais continuam com suas permissões: `/v1/clientes`, `/v1/produtos`,
`/v1/funcionarios` exigem OPERADOR para escrita e `/v1/usuarios` exige ADMIN —
teste `test_caixa_continua_sem_cadastros_e_usuarios` garante que o espelho de
leitura não afrouxou essas regras.

## Validação

- Backend: **404 passed** (5 novos testes de catálogo PDV).
- Desktop: **431 passed, 4 xfailed** (6 novos testes de contrato/UI do PDV).
