# Variações de produto, baixa otimista e transferência (PRD v3.2)

Implementado em 18/11/2026. Observação: o arquivo do **PRD v3.2 não está
versionado neste repositório** — a implementação segue a estratégia descrita
e os princípios dos PRDs v3.0/v3.1 presentes em `docs/PRD/`.

## O que foi entregue

### 1. Matriz de produtos (variações)
- `produto` ganhou `sku` (único por filial), `uuid` global (RF-FL-02),
  `produto_pai_id` e atributos `atrib_tamanho`, `atrib_marca`, `atrib_cor`.
- `POST /v1/produtos/variacoes/gerar` cria uma variante filha por combinação,
  com SKU automático (`PREFIXO-TAM-MARCA-COR`), uuid, estoque próprio e
  evento de sync. Idempotente (não duplica).
- A tela de Produtos tem o botão **Gerar variações** (uma combinação por
  linha `TAMANHO|MARCA|COR`).
- Atributos usam domínios pré-definidos sugeridos na UI (P/M/G/GG, marcas,
  cores) — evita "Azul" vs "azul escuro".

### 2. Baixa à prova de falhas (concorrência)
- `venda_service._baixar_estoque` agora usa `UPDATE produto_estoque SET saldo =
  saldo - :qtd WHERE filial_id = :f AND produto_id = :p AND saldo >= :qtd`.
  Se `rowcount == 0` → **409** com mensagem clara. Nunca gera saldo negativo.
- Validado com duas transações concorrentes reais no Postgres: a 1ª vende,
  a 2ª recebe 0 linhas afetadas, saldo final = 0.
- O desktop preserva o `status_code` do erro (`core/tarefas.py`) e o PDV
  exibe mensagem orientando a consultar o estoque e atualizar a busca.

### 3. Produto acabado vs. estoque por consumo
- Cada variação é produto acabado com estoque próprio no PDV (baixa direta).
- O estoque por consumo de matéria-prima permanece no módulo Produção/OS —
  o PDV continua leve (sem consultas extras por venda).

### 4. Multi-filial
- `transferencia_estoque` com fluxo de dois passos (§5.6): `enviada` (saída
  na origem com `UPDATE ... WHERE saldo >= qtd`) → `recebida` (entrada no
  destino). O destino só recebe o saldo após confirmação. Cancelamento
  estorna a origem.
- Rotas: `GET/POST /v1/estoque/transferencias`, `POST .../{id}/receber`,
  `POST .../{id}/cancelar`. Cliente desktop com os métodos correspondentes.
- Consulta cruzada de outra filial continua via cópia consolidada no Neon,
  com rótulo de defasagem (`docs/sync_agent_neon.md`).

### 5/6. Inventário rotativo e identificação
- Ajuste de estoque **exige motivo** na API e na UI (`perda`, `quebra`,
  `acerto`, `contagem` — domínio fechado `MotivoAjuste`), com kardex.
- O PDV consulta diretamente por SKU/uuid/código de barras
  (`GET /v1/produtos/buscar-sku/{termo}`) quando o termo não está no cache
  local — sem navegar menus de variações.

## Migration
`f9a0b1c2d3e4` — colunas de SKU/uuid/atributos, `transferencia_estoque`,
enums `estado_transferencia` e novas origens de movimento.

## Testes
- Backend: `test_variacoes_estoque.py` (SKU/uuid, motivo obrigatório, baixa
  otimista 409, transferência dois passos) — suíte completa **394 passed**.
- Desktop: `test_produtos.py` (gerar variações, buscar SKU) — **416 passed,
  4 xfailed**.
