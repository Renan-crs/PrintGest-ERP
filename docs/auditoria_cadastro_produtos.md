# Auditoria — cadastro de produtos, serviços e variações

Auditada em 20/11/2026 com as capturas enviadas e o harness
`scripts/medir_cadastro_produtos.py` (offscreen, 1024×768 e 1366×768).

## Geometria medida

| Cenário | Viewport do form | Conteúdo | Scroll | Preço de Venda (y) | Foto 2 (y) |
|---|---|---|---|---|---|
| Antes, 1366×768 | 546 px | 937 px | 251 px | abaixo da dobra | abaixo |
| Depois, 1366×768 | 546 px | 966 px | 280 px | **454 px (visível)** | 772 px (rolagem) |
| Depois, 1024×768 | 546 px | 966 px | 280 px | **454 px (visível)** | 772 px (rolagem) |

O conteúdo cresceu porque o botão de variações e as dicas ocupam espaço, mas
o campo de preço subiu para dentro da área visível — antes o operador precisava
rolar para conferir/alterar preço e estoque.

## Achados das telas enviadas

| # | Achado | Correção |
|---|---|---|
| 1 | Formulário longo: `FOTO 1/2` apareciam antes de precificação/estoque, empurrando preço para fora da tela | Seções reordenadas: `Cadastro → Precificação → Estoque → Imagens`. Fotos continuam disponíveis, mas no fim |
| 2 | Coluna **Ref** truncada (`#00…`) | Peso da coluna 1→2 (largura 56→93 px em 1366) e peso de "Item" 6→5 |
| 3 | Botão **Gerar variações** habilitado mesmo em "Novo Produto" (sem pai salvo) — clicar só mostrava aviso | Botão desabilitado até selecionar um produto salvo; reabilitado na seleção |
| 4 | Diálogo de variações pedia `TAMANHO\|MARCA\|COR` mas não mostrava os valores de domínio, apesar do texto "use sempre os mesmos valores" | Prompt agora lista tamanhos/marcas/cores já usados no catálogo e avisa que combinações repetidas são ignoradas (idempotência) |

## Fluxo de variações conferido

- Produto pai com `codigo` vira `prefixo_sku` (slug de até 8 caracteres).
- Cada linha `TAMANHO|MARCA|COR` gera uma filha com `produto_pai_id`, SKU único,
  uuid global, atributos próprios e linha em `produto_estoque` (saldo 0) na
  filial do usuário.
- Filha é sempre `tipo=produto` com `controla_estoque=True` — serviços são
  recusados com 400 no backend e o botão não aparece na tela de Serviços.
- Combinações repetidas no payload ou já existentes são ignoradas; ao regerar
  uma filha excluída, ela é reativada em vez de criar duplicata.
- O PDV indexa o SKU no cache local; bipe por SKU não faz request na primeira
  venda.
- Após gerar, `catalogos.invalidar("produtos")` + `recarregar()` atualizam a
  grade; a mensagem usa o número **real** de variantes criadas.

## Melhorias aplicadas na sequência (v0.5.26)

- **Diálogo estruturado** (`ui/modulos/dialogo_variacoes.py`): três combos
  editáveis (tamanho/marca/cor) com os domínios do catálogo, lista de
  combinações adicionadas, **preview do SKU** calculado com o mesmo slug do
  backend (`CV01-M-MARCAX-AZUL`), dedupe local, remoção e OK desabilitado
  enquanto não houver combinações.
- **Distinção pai/filha na grade**: variantes aparecem com o prefixo `↳` na
  coluna Item, e o filtro **Variações** mostra só registros com
  `produto_pai_id`.

## Limitações restantes

- O botão "Gerar variações" ainda não pede confirmação explícita antes de
  criar N variantes (desativa durante a requisição e mostra a contagem real).
- `schema.sql` segue defasado em relação às migrations (sem `sku`/`uuid`).

## Validação

- `test_produtos.py`: 17 testes (inclui preview SKU, dedupe, remoção,
  exigência de atributo, domínios sugeridos, filtro Variações e marcador `↳`).
- Suíte desktop completa: ver `CHANGELOG.md` da versão correspondente.
- Capturas regeneráveis com `desktop/.venv/Scripts/python.exe scripts/medir_cadastro_produtos.py`
  (saem em `analysis-assets/`, não versionadas).
