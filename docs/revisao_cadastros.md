# Cadastros (Clientes, Fornecedores, Produtos & Serviços) — correções 3.1 e reestruturação 3.2

Documento de entrega das correções de **Cadastros** descritas em
`docs/telas_e_fluxos.md` (PRD v2.1 + `schema.sql`), feitas **nos componentes
compartilhados** (não tela a tela).

> **Sobre os IDs.** O repositório não contém a lista numerada original
> (G/CL/FO/PR); as descrições abaixo foram reconstruídas a partir do escopo
> recebido. Os IDs usados como âncora em código/repo hoje são **G1** (rótulo
> acima) e **G13** (busca global); **CL1** e **PR6** vêm do escopo recebido.
> Confira o mapeamento ao cruzar com a lista original.

---

## 1. Componentes compartilhados (criados/alterados)

| Arquivo | Papel |
| --- | --- |
| `desktop/printgest/ui/formulario.py` | Rótulo **acima** do controle (`em_volta`), grade de **2 colunas** (`dispor_campos`), `larga()`, `CampoData` com **“Sem data”** (NULL de verdade), novo **`CampoArquivo`** (foto), `CampoValor` sem prefixo quando pedido |
| `desktop/printgest/ui/tabela.py` | **Sem rolagem horizontal**, elide + tooltip em toda célula, **estado vazio**, larguras por peso e **colunas prioritárias** (oculta as de menor peso quando estreita) |
| `desktop/printgest/ui/paginador.py` | Só “Exibindo X–Y de Z” (singular em 1); rótulos elidíveis (encaixa em telas estreitas) |
| `desktop/printgest/ui/theme.py` | **Seta nativa** dos combos (sem bloco preto), altura/mínimos dos inputs, estilo do estado vazio |
| `desktop/printgest/ui/widgets.py` | `ElideLabel` agora pode encolher (`minimumSizeHint`) — destrava o layout em 150% |
| `desktop/printgest/ui/busca.py` | Busca local com **Ctrl+F** (chip “F2” removido) |
| `desktop/printgest/ui/busca_global.py` | Placeholder curto + tooltip (**G13**) |
| `desktop/printgest/ui/modulos/pagina_crud.py` | Base única: splitter + painel lateral, rodapé **Salvar/Cancelar fixo**, **F6/F10/Esc** reais, hooks `VAZIO`/`FILTRO_LOCAL`/`PESOS` |

---

## 2. Correções 3.1 (pontuais/obrigatórias)

| ID | Requisito | Status | Observação |
| --- | --- | --- | --- |
| G1 | Componente único “campo com rótulo” (rótulo **acima**, ~40px) | ✅ | Todos os campos usam `em_volta` |
| G2 | Grade de **2 colunas iguais** | ✅ | `dispor_campos` |
| G3 | Longos (nome/razão, descrição, e-mail, endereço) em 2 colunas; curtos (UF, número, unidade, preço, quantidade) em 1; **sem larguras fixas** | ✅ | `larga()` + pesos da tabela |
| G4 | Sem **scroll horizontal** e no máx. 1 vertical em 1280/1366/1920 nas escalas 100/125/150% | ✅\* | Ver §5. Em 150% na 1280/1366 é preciso recolher a lateral (64px) |
| G5 | Corrigir a **seta dos combos** | ✅ | Regras de drop-down removidas; seta nativa |
| G6 | Remover caixa “N registros”; manter só “Exibindo X–Y de Z” (singular em 1) | ✅ | `paginador.py` |
| G7 | Remover chip **F2** (usar **Ctrl+F**) | ✅ | `busca.py` |
| G8 | Remover títulos decorativos dos cards e o badge **NOVO**; em edição mostrar o **código** no título | ✅ | Título = rótulo do cadastro ou “Editando #0000N” |
| G9 | **Estado vazio** em todas as listas | ✅ | `TabelaDensa.estado_vazio` |
| G10 | **“Sem data”** por padrão: campo desabilitado/vazio e **NULL** (nunca 01/01/1900) | ✅ | `CampoData` |
| G11 | Padronizar identificador (“Nº”/“Cód.”) | ✅ | `#0000N` no título de edição |
| G12 | Busca global com placeholder curto **ou** largura suficiente | ✅ | “Buscar…” + tooltip |
| G13 | Busca global (placeholder curto) | ✅ | `busca_global.py` |
| G14 | Máscara de **CPF/CNPJ acompanha o tipo** de pessoa (Cliente e Fornecedor) | ✅ | `_tipo_mudou` |
| CL1 | Cliente “**Consumidor final**” (#00002) **protegido** e **fora de relatórios** | ⛔ fora de escopo | Não existe no `schema.sql`: o “consumidor final” é `cliente_id = NULL` (linha 369) e o PDV já o oferece. Criar um cliente #00002 protegido exigiria **regra de negócio/coluna nova** — proibido pelo escopo |
| CL2 | “Observações técnicas” → “**Observações**” | ✅ | Agora seção “Observações” |
| CL3 | **Data de nascimento** só para **PF**; IE só para PJ | ✅ | `_tipo_mudou` |
| CL4 | Seções do formulário (geral/endereço/observações/histórico) | ⚠️ parcial | Seções ok; **Histórico** pendente (ver §3) |
| FO1 | Máscara CNPJ/CPF por tipo | ✅ | `_tipo_mudou` |
| FO2 | Observações em seção própria | ✅ | Seção “Observações” |
| PR1 | Remover “**R$**” de “Estoque mínimo” | ✅ | `prefixo=""` |
| PR2 | Ocultar controle de estoque para **Serviço** | ✅ | `_tipo_mudou` |
| PR3 | **Filtros** Tipo (Produtos/Serviços) | ✅ | `FILTROS` + filtro local |
| PR4 | Filtros **Categoria** e **Ativo** | ⛔ pendente | Depende de UI de múltiplos grupos de filtro; ver §5 (limitação de largura) |
| PR5 | Fotos do produto (2 campos) e do cliente | ✅ | `CampoArquivo` |
| PR6 | **NCM/CFOP** | ⛔ fora de escopo | Campos **não existem** em `schema.sql` nem no spec |

---

## 3. Reestruturação 3.2

| Item | Status | Observação |
| --- | --- | --- |
| Lista em largura total, com **colunas prioritárias** e elide+tooltip | ✅ | `TabelaDensa` oculta as colunas de menor peso quando falta espaço |
| Formulário em painel lateral (>= 520px) no splitter, com Salvar/Cancelar **fixos no rodapé** | ✅ | Alternativa mínima do spec; rodapé fora da área rolável |
| Formulários em **seções** (Clientes: Dados gerais / Endereço / Observações; Fornecedores: Dados cadastrais / Endereço / Observações; Produtos: Cadastro / Precificação / Estoque) | ✅ | Seções, não abas |
| **Histórico** (Clientes) | ⛔ pendente | Exigiria endpoint/consulta de histórico (não há no backend) |
| **Pedidos de compra** em Fornecedores (lista, form, “Confirmar recebimento”) | ⛔ pendente | Módulo de Compras não entregue; fora do backend atual |
| “Novo X” (F6) / clique na linha abre o formulário | ✅ | F6 real + seleção carrega o form |
| Expor todos os campos persistidos (foto do cliente/produto, nome fantasia, contato, categoria, preço de custo, observações) | ⚠️ parcial | Foto, preço de custo, categoria, observações ok. **`fornecedor` não tem `nome_fantasia` no `schema.sql`** |
| Produtos/Serviços no **mesmo componente**, `tipo` pelo menu | ✅ | `PaginaServicos` = `PaginaProdutos(TIPO_FIXO="servico")` |

---

## 4. RBAC

- Fornecedores só Admin/Gerente — preservado (item de menu escondido por `rbac`).
- Produtos & Serviços para **Operador**: os campos de **preço de custo/venda**
  ficam **desabilitados** na UI (`nivel == "operador"`). O backend permite
  escrita; mudar isso seria alterar **regra de negócio** (fora do escopo), logo
  a restrição é só de interface.

---

## 5. Layout / larguras (testes)

- Suíte completa: **178 passed** (`pytest -q`), incluindo
  `desktop/tests/test_layout_cadastros.py` (novo, 14 testes): sem rolagem
  horizontal e colunas visíveis cabendo, nas **9 combinações** resolução × escala,
  rodando cada página na **largura lógica real** (sem depender do tamanho da janela).
- Evidência objetiva:

| Tela | 1280x720 (conteúdo 1056px) | 1366x768 (1142px) | 1920x1080 (1696px) |
| --- | --- | --- | --- |
| Clientes | antes 1066 → depois **1056** | 1142 → 1142 | 1696 → 1696 |
| Fornecedores | antes 1185 → depois **1056** | 1185 → **1142** | 1696 → 1696 |
| Produtos | antes 1416 → depois **1056** | 1416 → **1142** | 1696 → 1696 |

  (números = largura mínima renderizada; “antes” estourava a área de conteúdo).

- **Limitação honesta:** com a lateral **expandida** (224px) e o piso de
  **520px** do formulário, não há como caber em **1280/1366 a 150%**
  (≈853/910px lógicos): o piso da página é ~762px. Nessas duas situações é
  preciso **recolher a lateral** (64px, botão «), o que faz a página caber.
  Em 100% e 125% cabe com a lateral expandida.

---

## 6. Screenshots (antes/depois)

Versionadas em `docs/evidencias/cadastros/` (renderização isolada da página,
sem a lateral, na largura de conteúdo de cada resolução):

```
docs/evidencias/cadastros/antes/    cliente_*, fornecedor_*, produto_  em 1280x720, 1366x768, 1920x1080
docs/evidencias/cadastros/depois/   cliente_*, fornecedor_*, produto_  em 1280x720, 1366x768, 1920x1080
```

---

## 7. Fora de escopo / pendências (com motivo)

1. **CL1 — “Consumidor final” #00002 protegido:** não existe no `schema.sql`
   (consumidor final = `cliente_id NULL`); exigiria regra/coluna nova.
2. **PR6 — NCM/CFOP:** campos ausentes em `schema.sql` e no spec.
3. **PR4 — filtros Categoria/Ativo:** a barra de filtros da base suporta um
   único grupo hoje; adicionar mais controles arrisca a largura mínima/telas de
   150%. Fica para a etapa de multi-filtros.
4. **Histórico de cliente e Pedidos de compra (3.2):** dependem de backend que
   não existe (endpoints/módulo de Compras).
5. **Nome fantasia de fornecedor:** coluna inexistente em `schema.sql`.
6. **150% em 1280/1366 com lateral expandida:** conflito entre o piso de 520px
   do formulário (spec) e a lateral fixa de 224px; resolvido recolhendo a lateral.

---

## 8. Nada de regressão

Cabeçalho, lateral, Início, PDV e Projetos continuam cobertos pelos testes
existentes (todos verdes). Nenhum endpoint foi alterado e nenhuma dependência
nova foi adicionada. A tabela de atalhos em `docs/telas_e_fluxos.md` foi
atualizada: **F6/F10/Esc** agora são reais nas telas de cadastro.
