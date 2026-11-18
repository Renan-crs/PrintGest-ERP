# Verificação da chamada e atualização automática entre endpoints (18/11/2026)

## Rotas × chamadas
- **173 rotas** no backend, **90 chamadas** no cliente desktop.
- Todas as chamadas têm rota correspondente. As 6 aparentes divergências são:
  CRUD genérico `/{entidade}` (4), baixa dinâmica `financeiro/{tipo}` (1) e
  um falso positivo do regex no f-string `buscar-sku/{quote(...)}` (1).

## Teste ponta a ponta (`test_verificacao_endpoints.py`)
Cadeia verificada com HTTP real contra o banco de teste:

1. cadastro de produto → evento `CRS` no outbox;
2. geração de variações → SKU + uuid + estoque próprio + evento;
3. leitura direta por SKU no PDV (`GET /produtos/buscar-sku/{sku}`);
4. entrada de estoque + venda → baixa otimista `WHERE saldo >= qtd`;
5. venda → movimento no caixa + evento de sync;
6. transferência entre filiais → documento `enviada` (saída na origem);
7. listagens sempre leem do banco e refletem as mudanças.

Resultado: **395 testes backend** (inclui este) e **416 desktop** (4 xfailed).

## Gaps encontrados e corrigidos nesta verificação
- **Tela de Transferências faltava**: os endpoints existiam, mas o desktop
  não expunha a interface. Adicionada a aba **Transferências** em Estoque, com
  enviar / confirmar recebimento / cancelar, e recarga automática após cada
  operação.
- Troca de abas de Estoque agora oculta a aba anterior antes do `deleteLater`
  (evita sobreposição transitória, mesmo padrão de Configurações).
