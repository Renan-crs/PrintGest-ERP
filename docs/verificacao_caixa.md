# Auditoria do fluxo de Caixa — abertura, movimentos, fechamento e lógica

Verificada em 19/11/2026. Escopo: backend (`financeiro_service`, rotas, modelos,
schemas, loop das 23:00), desktop (`PaginaCaixa`) e gravação no banco.

## Contrato API ↔ endpoints — consistente

| Tela (desktop) | API | Endpoint backend |
|---|---|---|
| `Abrir Caixa` (F6) | `abrir_caixa` | `POST /v1/financeiro/caixa/abrir` |
| `Lançar Movimento` (F7) | `movimento_caixa` | `POST /v1/financeiro/caixa/{id}/movimento` |
| `Fechar Caixa` (F9) | `fechar_caixa` | `POST /v1/financeiro/caixa/{id}/fechar` |
| Extrato (paginação) | `extrato_caixa` | `GET /v1/financeiro/caixa/{id}/extrato` |
| Estado atual | `caixa_atual` | `GET /v1/financeiro/caixa/atual` |

Chaves conferem: `valor_abertura`, `observacoes`, `tipo`, `valor`, `descricao`,
`valor_informado`. RBAC `require_perfis(CAIXA, GERENTE, ADMIN)`; OPERADOR → 403.
Fórmula de saldo idêntica na nominação:
`abertura + (entradas + suprimentos) − (saídas + sangrias)`;
`diferenca = informado − esperado`.

## Bugs encontrados e corrigidos

| Sev. | Achado | Correção |
|---|---|---|
| 🔴 | **Botões Abrir/Lançar/Fechar nunca reabilitavam após sucesso** — só no erro. F6/F7/F9 mascaravam o defeito; após 1 ciclo o botão "Abrir" ficava morto. | `_aplicar_estado` é agora a fonte única de habilitação (abierto/fechado × modo leitura), chamada também no sucesso. Campos de abertura/fechamento são limpos. |
| 🔴 | **Concorrência na abertura**: check-then-commit sem tratamento do índice único → 500 para o perdedor. | `IntegrityError` capturado → 409 com mensagem clara. Teste com 2 threads: [200, 409]. |
| 🟠 | Fechamento e movimento concorrentes sem lock → dois 200 possíveis. | `SELECT ... FOR UPDATE` em `_obter_caixa`. |
| 🟠 | Sangria acima do saldo criava saldo negativo. | Validação no serviço: `400` com saldo atual. |
| 🟠 | Caixa de outro usuário da mesma filial podia ser fechado/lançado/lido. | `_obter_caixa` filtra por `usuario_id`; rotas de movimento/extrato injetam `UsuarioDep`. |
| 🟠 | Fechamento automático exigia `minute == 0` (janela de 60 s) e podia pular o dia após restart. | Janela ampliada para qualquer minuto das 23:00 às 23:59 (uma vez por dia). |
| 🟡 | Diálogo de divergência quantizava diferente do backend e `diferenca="0.0"` era exibido como divergência. | UI quantiza com `ROUND_HALF_UP` (2 casas) e trata zero robustamente. |
| 🟡 | Extrato sem guarda de sequência (paginação antiga podia sobrescrever a atual). | `_seq_extrato` implementado, como em `recarregar`. |
| 🟡 | `Mapped[float]` em colunas `Numeric(14,2)`; doc de revisão dizia que fechamento automático era manual. | Tipos corrigidos para `Decimal`; documentação atualizada. |
| 🟡 | 423 de "usuário bloqueado" era rotulado "Modo leitura". | Título distinto quando a mensagem contém "bloqueado". |

## Lógica provada com testes novos

Backend (`backend/tests/test_caixa_logic.py`, 7 casos):
- 2º fechamento → 409; movimento em caixa fechado → 409;
- sangria 150 com saldo 100 → 400; sangria 40 → saldo 60;
- outro usuário da filial → 404 em extrato/movimento/fechamento;
- abertura concorrente → exatamente um 200 e um 409;
- fechamento automático fecha 2 caixas de filiais distintas com `informado = esperado`, `diferenca = 0`;
- cancelamento de venda gera `MovimentoCaixa(SAIDA)` e restaura o saldo;
- `valor_abertura < 0`, `valor_informado < 0` e `valor = 0` → 422.

Desktop (`desktop/tests/test_financeiro.py`, 5 casos):
- ciclo completo **por cliques** abrir → lançar → fechar → abrir (botões reabilitados);
- campos limpos após abrir/fechar;
- divergência recusada não fecha o caixa;
- `diferenca = 0` exibe "sem divergência";
- 423 de usuário bloqueado com título correto.

## Gravação no banco (verificada)

- Testes rodam em `printgest_test` (banco isolado), sem tocar em produção.
- Neon (somente leitura via MCP): head `a0b1c2d3e4f5` (nenhuma migration nova),
  índice único parcial `uq_caixa_aberto_filial_usuario` **presente**, 1 caixa
  aberto e 5 fechados — dados reais intactos.

## Ressalvas

- Fechamento automático usa `valor_informado = esperado` e diferença zero: é um
  fallback operacional, **não** substitui a conferência física do operador.
- Fecha caixas de todas as filiais (sem filtro) — comportamento existente.
- `updated_at` de `caixa` não tem `onupdate` (não muda em atualizações).
- Sangria agora respeita o saldo; se a política permitir saldo negativo, a
  regra precisa ser revertida explicitamente.

## Validação
Backend: **420 passed**. Desktop: **450 passed, 4 xfailed**.
