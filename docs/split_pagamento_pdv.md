# Split payment e melhorias UX do PDV

Implementado na v0.5.42 a partir do documento de análise/recomendações de UX.

## Split payment
- Botões grandes (`Dinheiro`, `Cartão de crédito`, `Cartão débito`, `Pix`,
  `Boleto`, `Fiado`) substituem o dropdown no painel de pagamento.
- Botão **"+ Adicionar forma de pagamento"** acrescenta linhas com forma e
  valor. O valor da forma principal é o total da venda menos a soma das extras.
- Backend: tabela `venda_pagamento` (uma linha por forma) com migration
  **aditiva** `d0e1f2a4b8c9`, aplicada ao Neon em 27/11/2026 com backup em
  branch `br-noisy-surf-b57v7cec` (LSN 0/3C85798).
- `venda_balcao.forma_pagamento` continua como **forma principal** para
  compatibilidade com relatórios, fiscal e eventos de sync legados.
- A soma das formas deve fechar com o total da venda (tolerância de R$ 0,01),
  senão 400. FIADO/BOLETO em qualquer posição geram título a receber; as demais
  entram no caixa com movimento próprio por forma.

## Outras melhorias visuais
- Botão **Finalizar venda** ganha destaque primário ao entrar o primeiro item.
- Lupa no campo de busca; botão **Item avulso** com borda tracejada.
- Botão de remover item por linha ampliado para 40×40 px (alvo de toque).
- Célula de desconto com destaque verde suave e tooltip com o valor aplicado.
- Indicador **online/offline** no cabeçalho do PDV, com aviso de que sem
  conexão a venda não pode ser registrada (não há venda offline de fato).

## Explicação do preço no carrinho
O backend já calcula faixas/modificadores e devolve `explicacao` e
`regra_aplicada` em cada item da venda. Após finalizar, o PDV mostra um resumo
da regra aplicada no painel de totais.

## Não implementado (fora do escopo desta entrega)
- Indicadores de status de impressora/gaveta/balança/leitor (não há contrato
  de status no backend).
- Produtos favoritos/mais vendidos (depende de endpoint de ranking).
- Teclado virtual e modo touch global (depende de plugin/distribuição).
- Contingência com vendas offline e sincronização posterior (projeto separado).
