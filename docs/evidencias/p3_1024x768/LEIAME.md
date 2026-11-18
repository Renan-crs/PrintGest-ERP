# Evidências P3 — matriz 1024×768 / 1366×768 @100%/125%

Capturas **depois** da rodada visual P3 (commit `28d2a3f`). Todas foram geradas
com `QApplication` offscreen e API falsa (`httpx.MockTransport`), sem backend:

- `*_1024x768_100.png` — `QT_SCALE_FACTOR=1`, janela lógica 1024×768.
- `*_1024x768_125.png` — `QT_SCALE_FACTOR=1.25`, janela lógica 819×614
  (equivale a 1024×768 físicos a 125% de DPI).
- `pdv_1366x768_100.png` — referência em tela maior.

## O que foi corrigido (visível nas capturas)

| Antes | Depois (evidência) |
|---|---|
| Janela travava em ~1248px (cabeçalho/rodapé com rótulos de largura fixa) | 1024×768 exata em todas as telas |
| Abrir o PDV/Histórico fazia a janela saltar para ~2096px | `pdv_*` e `pdv_historico_*` em 1024×768 |
| Filtros do Histórico cortados ("portar Ex...", "mpar filt...") | `pdv_historico_*`: filtros em duas linhas, sem corte |
| Filtros da OS empilhados numa coluna à direita | `os_lista_1024x768_100.png`: filtros em linha, lista larga |
| Botão "Ver" da grade cortado | `pdv_historico_*`: "Ver" e "⋯" inteiros |
| Cabeçalho "Valor unit." elidido para "or ur" | `pdv_*`: "Unit." legível |
| Barra de itens do PDV cortada em 125% | `pdv_1024x768_125.png`: barra em duas linhas |
| Aba anterior sobreposta ao trocar Configurações (deleteLater assíncrono) | `integracoes_1024x768_100.png`: aba limpa, formulário rolável |
| 8 abas de Configurações cortadas numa linha | `estacoes_1024x768_100.png`: duas linhas de 4, rótulos completos |
| Matriz 1024×768 (mínimo) e 1366×768 | `pdv_1024x768_minimo.png` (sidebar colapsada) e `pdv_1366x768_revisado.png` (sidebar expandida) |

## Reprodução

O harness usa `QT_QPA_FONTDIR=C:\Windows\Fonts` para que o offscreen renderize
fontes, `QT_SCALE_FACTOR` para simular DPI e `show()` seguido de `resize()` para
que o `QMainWindow` aceite a geometria. Os testes permanentes de regressão estão
em `desktop/tests/test_layout_p3.py`:

```
cd desktop
.venv\Scripts\python.exe -m pytest tests/test_layout_p3.py -q
```
