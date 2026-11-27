# VF unitário ou total do fornecedor

Implementado na v0.5.41. Corrige o caso em que o fornecedor informa o valor
**da quantidade inteira** (ex.: R$ 35,00 por 24 adesivos de vinil) e o sistema
tratava esse número como preço unitário, gerando R$ 2.047,92.

## Regra

| Modo | VF informado | CP | VO / total da linha | Unitário exibido |
|---|---|---|---|---|
| `unitario` (padrão) | preço de **uma** unidade | VF × 2,30 | VO × quantidade | VO |
| `total` | montante cobrado por **toda a quantidade** | VF × 2,30 | VO (montante) | VO ÷ quantidade (4 casas, informativo) |

Exemplo real: VF 35,00 (total de 24) → CP 80,50 → **total 85,33** → unitário
informativo 3,5554 (exibido 3,56). O total **nunca** é recalcado como
unitário arredondado × quantidade (3,56 × 24 = 85,44 ≠ 85,33).

## Onde escolher

- **Grade de itens do orçamento:** checkbox "VF é o total da quantidade" no
  editor; ao editar a coluna VF diretamente, o modo do item é preservado.
- **Modal de cotações:** checkbox "VF informado é o TOTAL da quantidade".
  O tipo viaja no payload e fica gravado em `os_item_cotacao.vf_tipo`,
  necessário porque `PUT /selecionar` não recebe corpo.
- Padrão `unitario` mantém 100% de compatibilidade com cotações antigas e com
  o caso canônico `87,35 → 200,91 → 212,96`.

## Snapshot

`snapshot_preco` passa a conter `vf_tipo`, `quantidade`, `vo_unitario` e
`vo_total`, além das chaves antigas. A UI mostra natureza do VF e ambos os
valores no comparativo de cotações.

## Migration

`a7b8c9d0e1f2` — **aplicada ao Neon em 27/11/2026** com backup em branch
`br-lucky-glade-b5q6m8ra` (`backup-pre-migration-vf-tipo-20261127`, LSN
0/3C76F10). Aditiva: coluna `vf_tipo` com default `'unitario'` e CHECK.
Nenhum dado existente foi alterado.
