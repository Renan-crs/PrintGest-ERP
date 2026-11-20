# Verificação dos cenários financeiros reais

Verificada em 20/11/2026. Atendimento aos cenários relatados pelo operador:

1. fechar caixa em dia sem lançamento / com serviços já pagos;
2. cliente pagou o sinal e falta o restante;
3. cliente parcelou o pagamento.

## Onde o dinheiro entra/sai do caixa (depois das correções)

| Origem | Movimento | Valor |
|---|---|---|
| Venda balcão (dinheiro/cartão/PIX) | `ENTRADA` em `venda_service._registrar_no_caixa` | `valor_total − sinal já recebido` |
| Sinal/adiantamento confirmado | `ENTRADA` em `adiantamento_service.exigir_e_registrar` | valor da exigência (`sinal_pct` ou 100%) |
| Baixa de `ContaReceber` | `ENTRADA` em `financeiro_service._baixar` | `pago_agora`, com `conta_receber_id` |
| Cancelamento de venda | `SAIDA` em `venda_service.cancelar` | `valor_total`, se o caixa ainda estiver aberto |
| Sangria/suprimento | `SAIDA`/`ENTRADA` em `financeiro_service.registrar_movimento` | valor informado |

## Cenário A — fechamento sem movimento / serviços já pagos

**Antes:** `valor_informado` era obrigatório (`ge=0`) na API e na tela. Mesmo
com R$ 0,00 e extrato vazio, o operador precisava "declarar" um número — o
sistema não tinha noção de "nada a conferir".

**Depois:**
- `FecharCaixaIn.valor_informado` é opcional; quando omitido, o backend adota
  `valor_esperado` (mesma política do fechamento automático) e grava `diferenca = 0`.
- A tela permite F9 com o campo vazio: pergunta "Conferência dispensada — usar
  o valor esperado (R$ X)?" e envia o payload sem o campo.
- Caixa com abertura 0 e nenhum movimento fecha com `0/0/0` sem erro.
- Serviços já pagos por sinal não geram nova entrada na execução/entrega: O.S.
  nunca lança `valor_total` no caixa; a entrada é apenas a do sinal.

## Cenário B — sinal pago, restante pendente

**Antes:** a exigência vinha dos flags do cliente (`sinal_pct`), mas
`valor_sinal` era denormalizado e ignorado; o restante existia só como cálculo
em `OsOut.saldo`, sem lastro em `ContaReceber`. Consequência: o dashboard "a
receber" não via o restante.

**Depois:**
- `os_service.criar`/`converter_em_os` gravam em `valor_sinal` o valor
  **efetivamente recebido** pela exigência do cliente.
- O restante (`valor_total − sinal`) passa a ser `ContaReceber` `ABERTA`,
  vinculada à O.S., com vencimento hoje.
- `OsOut.saldo` (total − sinal) agora corresponde ao título aberto.

**Venda balcão com sinal:** havia **duplicação** —`sinal` (entrada própria) +
`valor_total` (entrada da venda) contavam o mesmo dinheiro duas vezes. Agora a
venda lança apenas `valor_total − sinal`; o total de entradas confere com o
valor da venda.

## Cenário C — parcelamento e FIADO

- `parcelas` era puramente informativo. Para **boleto**, o restante agora gera
  N títulos (`parcela`/`total_parcelas`, vencimentos espaçados de 30 dias), com
  a última parcela absorvendo o arredondamento. Para cartão/dinheiro/PIX o
  recebimento é imediato e `parcelas` continua informativo (parcelamento com a
  operadora, não com o cliente).
- **FIADO** não entrava no caixa **nem** gerava conta — o valor ficava fora do
  sistema financeiro, apesar da docstring afirmar o contrário. Agora gera
  `ContaReceber` `ABERTA` do total (ou do restante, se houve sinal).
- A **baixa** de `ContaReceber` (parcial ou total) passa a gerar
  `MovimentoCaixa(ENTRADA, conta_receber_id=...)` no caixa aberto de quem
  baixou. Antes a baixa era só contábil, contradizendo `telas_e_fluxos.md`
  ("compra/recebimento gera lançamento automático") e o FK existente.

## Validação

Backend (`test_cenarios_financeiros.py`, 6 casos + ajuste em `test_adiantamento.py`):
- fechamento com `{}` (caixa 0 e caixa 120) → `informado = esperado`, `diferenca = 0`;
- venda com sinal 50% → duas entradas de 50 (total 100, sem duplicação);
- FIADO → título aberto, zero movimento de caixa;
- boleto em 3 parcelas → 3 títulos `1/3..3/3` somando 100;
- O.S. com sinal 30% de 200 → `valor_sinal=60`, `saldo=140`, título aberto de 140;
- baixa parcial 40 + final 60 → dois movimentos de caixa com `conta_receber_id`.

Desktop (`test_financeiro.py`): F9 com campo vazio → confirmação de
conferência dispensada → fechamento sem divergência.

**Suítes:** backend **426 passed**, desktop **451 passed, 4 xfailed**.
Neon: head `a0b1c2d3e4f5` — nenhuma migration nova (todas as correções são de
lógica; `conta_receber` já tem `parcela`, `total_parcelas`, `vencimento` e FKs).

## Ressalvas / não implementado

- Parcelamento em **cartão de crédito** continua informativo (não gera títulos
  para o cliente).
- Não há gate "entregue exige pagamento resolvido" (PRD v3.0 §3.8) — uma O.S.
  com título em aberto ainda pode ser marcada como entregue.
- `repetir_pedido` não repassa `pagamento_confirmado`: clientes com adiantamento
  recebem 400 nesse fluxo (fora do escopo destes cenários).
- Baixa sem caixa aberto mantém o título baixado, mas sem movimento físico
  (mesma política do adiantamento sem caixa).
- Histórico anterior não é reescrito: vendas antigas com sinal podem ter
  duplicação no extrato; as correções valem para documentos novos.
