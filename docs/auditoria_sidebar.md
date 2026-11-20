# Auditoria do sidebar — altura, espaçamento e links

Auditada em 20/11/2026. Harness de medição: `scripts/medir_sidebar.py`
(offscreen, desktop venv).

## Geometria medida (ADMIN)

| Cenário | Sidebar | Conteúdo do menu | Scroll | Botões visíveis |
|---|---|---|---|---|
| 1366×768, fonte padrão | 224×687 px | 592 px | 0 (não precisa) | 17/17 |
| 1366×768, fonte 22 px (≈125%) | 224×687 px | 766 px | **máx. 174 px** | 17/17 |
| 1024×768, colapsado | 64×687 px | 462 px | 0 | 17/17 |

Antes das correções, o menu do ADMIN não tinha `QScrollArea` e o colapso
escondia **todos** os botões: em 1024×768 só "Início" navegava.

## Correções aplicadas

| Sev. | Achado | Correção |
|---|---|---|
| 🔴 | Colapso automático em 1024×768 escondia todos os links | Trilho de 64 px mantém os 17 botões visíveis com rótulos curtos (`CLI`, `FIN`, …), tooltips/accessibleName completos; clique navega normalmente |
| 🔴 | Menu do ADMIN podia cortar o grupo SISTEMA (fonte maior / DPI 125%) | Lista envolvida em `QScrollArea` (`menuScroll`) com barra vertical sob demanda; `sizePolicy` Ignored impede crescimento da janela |
| 🟠 | 6 ids autorizados caíam em `PaginaEmConstrucao` | `rel_vendas`/`rel_clientes`/`rel_servicos`/`rel_aniversariantes` abrem `PaginaRelatorios` já na aba correta; `pedido_compra` e `estoque_mais_vendidos` (sem implementação/API) removidos de `ITENS_INTERNOS` |
| 🟠 | BuscaGlobal visível mas inútil para CAIXA; F2/F3 anunciados no rodapé | Campo oculto quando nenhuma entidade é pesquisável; atalhos e dicas filtrados por `pode_abrir` |
| 🟠 | Sinal `abrir_registro` da busca nunca conectado | Conectado: seleciona o registro na tabela do módulo de destino |
| 🟡 | `fornecedor` visível só para gerente, mas backend aceitava OPERADOR | Backend alinhado ao menu: `/v1/fornecedores` agora exige GERENTE+ |
| 🟡 | Sem tooltips/accessibleName nos botões do menu e no «/» | Adicionados (inclusive no trilho colapsado) |

## Espaçamento mantido

- Sidebar: `setFixedWidth(224)` (64 no colapso), margens `10,14,10,14`, spacing `2`.
- QSS: grupo `font-size:10px; padding:10px 5px 4px`; botão nav `font-size:13px; padding:7px 10px`.
- `addStretch(1)` foi substituído pelo `QScrollArea` com stretch 1 — o espaço
  excedente continua distribuído, e o escasso gera rolagem em vez de corte.

## Testes novos (`test_tela_principal.py`)

- colapso em 1024×768 mantém 17/17 botões visíveis, rótulos curtos e clique navega;
- `QScrollArea#menuScroll` presente e redimensionável;
- fonte 22 px → `scroll_max > 0` e último item (`Consolidação`) alcançável;
- CAIXA sem busca global e sem dicas F2/F3; ADMIN com busca;
- `abrir_registro` seleciona o cliente na tabela;
- links granulares de relatório não caem no placeholder.

**Suítes:** backend 439 passed; desktop 461 passed, 4 xfailed.

## Ressalvas

- O trilho colapsado usa abreviações textuais (sem ícones), para não exigir
  mudança de tema/asset. Os tooltips trazem o rótulo completo.
- `schema.sql`/docs antigas podem citar `pedido_compra` como link disponível;
  não há API nem tela implementadas, por isso o id foi removido do RBAC.
