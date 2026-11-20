# Verificação de Produtos, Serviços, Variações e Estoque

Verificada em 20/11/2026.

## Contrato API ↔ endpoints — consistente

Todos os paths chamados pela UI existem e os envelopes casam com o backend:

- `GET/POST/PUT/DELETE /v1/produtos`, `GET/POST/PUT/DELETE /v1/categorias`;
- `POST /v1/produtos/variacoes/gerar` (201) com `produto_pai_id`,
  `prefixo_sku`, `variacoes[{tamanho,marca,cor,preco_venda,codigo_barras}]`;
- `GET /v1/produtos/buscar-sku/{termo}` (OPERADOR) e o espelho
  `/v1/pdv/produtos/buscar-sku/{termo}` (CAIXA) usado no PDV;
- `GET /v1/estoque`, `/resumo`, `/reposicao`, `/{id}/kardex`,
  `POST /v1/estoque/movimentar`.

RBAC: produtos/categorias/variações exigem OPERADOR; preço agora é restrito à
gerência no backend (antes só na UI).

## Regras de negócio confirmadas

- Cada variante filha é **produto acabado**: `produto_pai_id`, `sku` único por
  filial, `uuid` global, `atrib_tamanho/marca/cor`, `controla_estoque=True` e
  linha própria em `produto_estoque` (saldo 0) na filial do usuário.
- `venda_service` baixa estoque da **variante** com `UPDATE ... WHERE saldo >=
  qtd` (409 sob concorrência) — nunca saldo negativo.
- `buscar_por_sku` casa `sku`, `uuid`, `codigo_barras` e `codigo`, somente
  produtos ativos do tipo `produto`.
- Serviço não controla estoque; `estoque_service` recusa `tipo=servico`.

## Bugs encontrados e corrigidos

| Sev. | Achado | Correção |
|---|---|---|
| 🔴 | **Serviço podia gerar variações**: herança de `tipo` do pai + `controla_estoque=True` criava "serviço com estoque", exposto no PDV por SKU e com baixa de estoque. | Backend recusa pai `servico` (400); filha sempre `tipo=produto`; `buscar_por_sku` filtra tipo; botão "Gerar variações" removido da tela de Serviços. |
| 🔴 | **`prefixo_sku` aceitava só 20 caracteres**, mas a UI envia `codigo` de até 30 — gerava 422. | Limite alinhado a 30. |
| 🟠 | **RBAC de preço só no cliente**: operador podia alterar `preco_custo`/`preco_venda` via API. | `crud_factory` reforça `GERENTE` para campos de preço em POST/PUT. |
| 🟠 | Soft-delete do pai deixava filhas ativas e órfãs no catálogo/PDV. | `ao_desativar` desativa as filhas na mesma transação. |
| 🟠 | Kardex de venda gravava SAIDA com quantidade **positiva**, enquanto movimentação manual usa negativa. | SAIDA passa a `-quantidade` (entrada segue positiva). |
| 🟠 | `VariacaoIn` aceitava linha sem nenhum atributo, gerando SKU igual ao prefixo; idempotência ignorava filha excluída para sempre. | Validador por linha (422); reativação da filha excluída ao regerar. |
| 🟡 | `codigo` da filha com só 4 hex de entropia e `IntegrityError` não tratada → 500. | 8 hex + verificação de unicidade; conflito → 409 com rollback. |
| 🟡 | Código de barras duplicado aceito; `uuid` sem UNIQUE no banco. | Validação de barras no serviço. UNIQUE em `uuid` exigiria migration (não feita — ver ressalvas). |
| 🟡 | `limit=1000` de categorias era cortado a 200 sem aviso; erro silencioso. | Continua limitado a 200 (contrato da fábrica), mas a falha agora aparece como tooltip no combo, sem modal. |
| 🟡 | Status 401/423/403 descartados na tela de produtos e no `_salvar` genérico. | Callbacks com 2 parâmetros; títulos específicos. |
| 🟡 | PDV não indexava `sku` do catálogo: toda bip por SKU fazia request ao servidor. | `_por_codigo` agora inclui o SKU da variante. |
| 🟢 | "Gerar variações" sem trava de duplo clique e mensagem com nº solicitado, não nº criado (idempotência). | Botão travado; mensagem usa `len(resposta.data)`. |

## Validação

Backend (`test_produtos_variacoes_contrato.py`, 8 casos + ajuste em
`test_vendas.py`): pai serviço 400, linha sem atributo 422, prefixo 30 aceito,
filha com estoque e pai sem estoque, SKU encontra a filha, soft-delete em
cascata, reativação idempotente, operador 403 para preço e 200 para nome,
estoque recusa produto inativo.

Desktop (`test_produtos.py` + `test_venda_balcao.py`, 4 casos novos): serviços
sem botão de variações, payload/count reais no botão, linha vazia não chama a
API, SKU exato resolvido pelo cache do PDV.

**Suítes:** backend **437 passed**, desktop **455 passed, 4 xfailed**.
Mutação: **11/11 mortos**. Neon: head `a0b1c2d3e4f5` — nenhuma migration nova.

## Auditoria de mutabilidade (testes de mutação)

Harness: `scripts/testes_mutabilidade.py` (executar com
`backend/.venv/Scripts/python.exe scripts/testes_mutabilidade.py`). Ele aplica
11 mutações controladas, roda o teste correspondente e **restaura o arquivo em
`finally`**, inclusive se o pytest falhar. Resultado: **11 mortos, 0
sobreviventes**.

| Mutante (alteração injetada) | Teste que o matou |
|---|---|
| Serviço aceito como pai de variação | `test_variacao_exige_produto_pai` |
| Filha com `controla_estoque=False` | `test_filha_tem_estoque_proprio_e_pai_nao` |
| Saldo inicial da filha = 5 | `test_filha_tem_estoque_proprio_e_pai_nao` |
| RBAC de preço desligado | `test_operador_nao_altera_preco` |
| SKU/uuid/pai/tipo alteráveis via PUT | `test_campos_de_identidade_sao_imutaveis` |
| Soft-delete sem cascata nas filhas | `test_soft_delete_do_pai_desativa_filhas` |
| Produto inativo aceito em movimentação | `test_estoque_nao_movimenta_produto_inativo` |
| Kardex de SAIDA com quantidade positiva | `test_venda_baixa_estoque_e_registra_kardex` |
| `prefixo_sku` limitado a 10 | `test_prefixo_sku_de_30_caracteres_e_aceito` |
| Variação sem atributo aceita pelo schema | `test_schema_rejeita_variacao_sem_atributo` |
| PDV sem índice de SKU no cache | `test_sku_exato_adiciona_pelo_cache_sem_chamar_endpoint` |

**Mutabilidade de cadastro (nova regra):** `sku`, `uuid`, `produto_pai_id` e
`tipo` são campos de identidade — `PUT /v1/produtos/{id}` rejeita alterações
com 400 (reenviar o mesmo valor é aceito, como faz a UI). O saldo de estoque
não é campo de cadastro e permanece intacto após PUT (provado por teste).

## Ressalvas

- `uq(uuid)` e `uq(codigo_barras)` no banco, e o `CHECK` que impede
  `servico + controla_estoque`, exigiriam migration em produção — não feitas
  sem autorização. Hoje são garantidas na camada de serviço/API.
- `schema.sql` está defasado (não tem `sku`/`uuid` e usa `codigo UNIQUE`
  global); a fonte da verdade são as migrations Alembic.
- `limit=1000` de categorias continua sendo reduzido a 200 pela fábrica de
  CRUD (mesmo padrão do PDV, que usa o espelho `/v1/pdv/produtos` com teto
  5000).
- `reposicao.status = "atencao"` quando `estoque_minimo = 0`, e
  `total_bobinas` é derivado de `dimensoes` — rótulos aproximados, sem impacto
  nos saldos.
