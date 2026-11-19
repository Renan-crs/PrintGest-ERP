# Verificação das chamadas API ↔ endpoints — Tela Início

Verificado em 19/11/2026.

## Contrato API (consistente)

| Chamada desktop | Endpoint backend | Status |
|---|---|---|
| `resumo_dashboard(dias)` | `GET /v1/dashboard/resumo?dias=7\|30` | ✅ |
| `testar_comunicacao()` | `GET /health` | ✅ |
| `situacao_licenca()` | `GET /v1/licenca` | ✅ |
| `logout()` | `POST /v1/auth/logout` | ✅ |

- `Query(dias, ge=7, le=30)` aceito; combo só envia 7 ou 30.
- Envelope `ItemResponse` desembrulhado em `_tratar()` (`resp.json()["data"]`).
- **Todas as chaves** esperadas pela tela existem no `DashboardResumoOut`:
  `vendas_hoje_qtd`, `vendas_ontem_qtd`, `vendas_hoje_valor`, `filial_nome`,
  `a_receber_vence_hoje`, `a_receber_atrasado`, `a_pagar_vence_hoje`,
  `vendas_7_dias`, `faturamento_previsto`, `projetos_em_producao`,
  `projetos_atrasados`, `estoque_abaixo_minimo`, `entregas_hoje`,
  `pendencias` (com `caixa_aberto`, `caixa_saldo`, `orcamentos_aguardando_aprovacao`,
  `artes_aguardando_cliente`, `os_prontas_retirada`, `contas_pagar_hoje`,
  `nfce_rejeitadas`).
- Sub-objetos `entregas_hoje` (`os_id`, `numero`, `cliente_nome`, `servico`,
  `prazo`, `status`, `atrasada`) e séries (`data`, `valor`) conferem.
- `/v1/licenca` e `/health` registrados e consumidos corretamente.
- Nenhuma chamada a rota inexistente.

## Bug encontrado e corrigido

**`PaginaInicial` não implementava `recarregar()`**, mas `TelaPrincipal._navegar`
chamava `self._pagina_inicio.recarregar()` ao voltar ao Início. Resultado: os
KPIs/pendências ficavam parados a sessão inteira (só atualizavam no arranque,
troca de dias ou botão retry) — apesar do comentário no código dizendo o
contrário.

Corrigido com:
```python
def recarregar(self) -> None:
    self._carregar_resumo()
```
e teste de regressão `test_voltar_ao_inicio_recarrega_kpis` que navega para
outro módulo, volta ao Início e confirma uma nova chamada ao endpoint.

## Ressalvas (não divergência de contrato)
- `vendas_7_dias` mantém esse nome mesmo quando `dias=30` — compatível hoje
  (tela e backend usam a mesma chave), mas frágil se alguém renomear.
- A razão social da home vem de `filial_nome` do resumo, não de
  `/v1/config/empresa` — intencional.

## Validação
Backend: 399 passed. Desktop: 425 passed, 4 xfailed.
