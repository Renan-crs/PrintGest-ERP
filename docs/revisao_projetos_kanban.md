# Projetos (Quadro Kanban) — Fase 1 (Núcleo): backend + tela

Documento de entrega da **Fase 1** do módulo **Projetos** descrito no
`PRD — Módulo Projetos (Quadro Kanban)` (v1.0.0, 17/10/2026), que substitui o
modelo "1 projeto = 1 O.S." do PRD v2.1.

> **Escopo desta entrega.** Backend da Fase 1 (Núcleo) — modelo de dados,
> migração, API do quadro/listas/cartões e as regras de visibilidade — **e a
> tela do desktop** (`ui/modulos/projetos.py`), que passou a consumir
> `/v1/projetos`. O antigo quadro sobre `/v1/os` (ver
> `docs/revisao_projetos.md`) foi substituído; `PaginaOS`/`PaginaOrcamento`
> seguem intactas. Etiquetas, checklists, comentários e anexos são a Fase 2.

---

## 1. Abordagem: aditiva, sem quebrar o que existe

Tudo entrou sobre um **namespace novo**, `/v1/projetos`:

- `/v1/os`, `ordem_servico` e o quadro atual **não foram alterados**;
- nenhuma tabela ou coluna existente mudou (migração **reversível** e só de
  criação);
- `ordem_servico.posicao_kanban` (campo descartado pelo PRD) **não existe** neste
  schema — não houve o que remover;
- **nenhuma dependência nova**.

Isso atende à restrição vigente ("sem *breaking changes*") e permite trocar a
origem da tela só quando a API estiver madura.

---

## 2. Modelo de dados (PRD §9)

Migração: `backend/alembic/versions/e7c1d4a2b9f6_modulo_projetos_quadro_cartao.py`
(`down_revision = d4b5c6e7f8a0`). Revisível: `upgrade` cria, `downgrade` remove
(tabelas **e** os tipos `tipo_lista`/`origem_membro`).

| Tabela | Papel | Pontos-chave |
| --- | --- | --- |
| `quadro` | Um por filial (`uq_quadro_filial`) | semente automática na 1ª consulta |
| `quadro_lista` | Colunas configuráveis | `tipo`, `status_os` (mapa p/ O.S., RN2), `usuario_dono_id` (lista pessoal, PV3), `fornecedor_id` (terceiros), `arquivada`, `posicao` |
| `cartao` | Unidade de trabalho | `ordem_servico_id` **único e nulo** (0..1 O.S. — RN1), `versao` (controle otimista), `concluido`, `data_*`, `terceiro_*`, `arquivado` |
| `cartao_membro` | Fonte **única** da visibilidade | `origem ∈ {manual, lista, atribuidor}` (PV3/PV4) |

Enums novos: `tipo_lista` (`orcamento`, `usuario`, `aprovacao`, `producao`,
`terceiro`, `final`, `livre`) e `origem_membro`. O `status_os` já existia e é
apenas referenciado (`create_type=False`).

**Listas semente** (PRD §4.1 / decisão D4, até o responsável informar os nomes
reais):

| Lista | `tipo` | `status_os` |
| --- | --- | --- |
| Orçamento | `orcamento` | `aberto` |
| Aguardando | `aprovacao` | `aprovado` |
| Em produção | `producao` | `producao` |
| Pronta | `final` | `pronta` |
| Entregue | `final` | `entregue` |

---

## 3. API (`/v1/projetos`)

| Método | Rota | Perfil | Observação |
| --- | --- | --- | --- |
| GET | `/quadro` | Operador+ | quadro + listas com **contagem** já filtrada por visibilidade (PV5) |
| POST | `/quadro/listas` | Admin/Gerente | cria lista (`tipo`, `status_os`, dono) |
| PATCH | `/quadro/listas/{id}` | Admin/Gerente | renomeia, troca tipo/status/dono e **reordena** (`posicao` = índice) |
| PATCH | `/quadro/listas/{id}/arquivar` | Admin/Gerente | RN6: arquiva (cartões permanecem) |
| DELETE | `/quadro/listas/{id}` | **Admin** | exclusão definitiva; bloqueia se houver cartões ativos |
| GET | `/cartoes` | Operador+ | filtros `q`, `lista_id`, `arquivado`, `sou_membro`; paginado |
| POST | `/cartoes` | Operador+ | cria cartão |
| GET | `/cartoes/{id}` | Operador+ | **404** se invisível (PV2) |
| PATCH | `/cartoes/{id}` | Operador+ | edita; exige `versao` (409 se desatualizada) |
| PATCH | `/cartoes/{id}/mover` | Operador+ | **atômico**: lista + posição + membros + versão |
| PATCH | `/cartoes/{id}/arquivar` · `/restaurar` | Operador+ | RN6 |
| PATCH | `/cartoes/{id}/atribuir` | Operador+ | WF2/PV4 |
| POST | `/cartoes/{id}/membros` · DELETE `.../membros/{usuario_id}` | Operador+ | membros manuais |

RBAC: o módulo é de operação (**Admin, Gerente, Operador** — PRD §1.5); **Caixa
não acessa** (403). A estrutura do quadro é de gestores; a exclusão definitiva é
só do Admin (RN6).

---

## 4. Regras implementadas

### 4.1 Visibilidade (PV1–PV5) — no servidor

Um **único predicado** (`projetos_service._condicao_visivel`) é aplicado em toda
consulta (quadro, lista, busca, contagem, obter e mover):

- **PV1:** sem membros, o cartão é da **equipe** (todo usuário ativo da filial
  com acesso ao módulo);
- **PV2:** com ≥ 1 membro, restringe-se a **membros + Admin/Gerente**. Cartão
  invisível devolve **404**, nunca 403 — não confirma existência;
- **PV3:** mover para uma **lista pessoal** adiciona o dono como membro
  (`origem = lista`); ao sair, essa marcação é removida (membros manuais/de
  atribuição permanecem);
- **PV4:** quem **atribui** a outro usuário, e **não é gestor**, vira
  acompanhante (`origem = atribuidor`) — o cartão não fica órfão;
- **PV5:** as **contagens** por lista respeitam a visibilidade do consultante.

A visibilidade é **derivada** de `cartao_membro` e **nunca** armazenada em
`cartao`.

### 4.2 Ordenação fracionária (§10)

`posicao` guarda um racional (`NUMERIC(24,12)`) para inserir no meio sem
renumerar a coluna. A API expõe um **índice** (0-based); o servidor converte em
fração e, quando o passo se esgota (duas posições vizinhas na precisão máxima),
**rebalanceia** a lista com passo uniforme e refaz a inserção.

### 4.3 Movimentação atômica e versão otimista

`mover` grava lista + posição + membros + `versao` numa **única transação**:
falhou uma regra, nada muda (o cartão "volta"). Toda escrita lê `versao` do
cliente e devolve **409** se outro usuário gravou antes.

---

## 5. Testes

`backend/tests/test_projetos.py` — **20 testes**, cobrindo: semente das listas,
CRUD de listas com dono/contagem, criar/editar/arquivar/restaurar cartão,
movimentação atômica, **rebalanceamento** (forçado por posições vizinhas no
limite da precisão), 409 por versão obsoleta, limpeza de campos com `null`
(PATCH parcial), PV1/PV2 (404 para não membro e some da busca), PV3 (entra/sai da
lista pessoal), PV4 (atribuidor acompanhante), PV5 (contagem), membros manuais,
RBAC (Caixa 403; estrutura só gestor; exclusão só admin), exclusão de lista com
cartões, e **não-regressão** (`GET /v1/os` segue respondendo).

Suíte do backend: **142 testes** verdes (122 anteriores + 20 novos).

### 5.1 Tela do desktop (Fase 1 UI)

`desktop/printgest/ui/modulos/projetos.py` substitui a antiga `PaginaProjetos`
(que ficava em `ui/modulos/os.py`) e consome `/v1/projetos`:

- **Quadro dinâmico** — `QuadroKanban.definir_colunas()` reconstrói as colunas a
  partir de `GET /quadro`; os cartões vêm de `GET /cartoes` (uma consulta) e são
  agrupados por `lista_id`, respeitando a visibilidade calculada no servidor;
- **Arrastar-e-soltar / menu "Mover para"** — o soltar informa o **índice**
  (novo 3º argumento de `movido`, pela metade do cartão); a página converte para
  a semântica do servidor (mesma lista desconta o próprio cartão; menu anexa ao
  final) e grava via `PATCH /cartoes/{id}/mover` com a `versao` lida (409 em
  conflito recarrega o quadro);
- **Ficha do cartão** (`DialogoCartao`) — título, descrição, datas, lembrete,
  responsável (atribuição), concluído, arquivar/restaurar e **membros** (add/remover;
  restringem a visibilidade);
- **Gestão de listas** (`DialogoListas`) — criar, renomear, arquivar e (só Admin)
  excluir. Botão visível apenas para Admin/Gerente; o backend reforça (403);
- **Modo leitura** — nada é arrastável nem gravável.

`desktop/tests/test_projetos.py` — **25 testes** (quadro, colunas do servidor,
busca, atraso, movimentação com índice/versão, reordenação interna, modo leitura,
RBAC de estrutura e os diálogos de cartão e de listas).

Suíte do desktop: **240 testes** verdes.

---

## 6. Decisões tomadas (para revisão)

1. **Aditivo** (namespace `/v1/projetos`), conforme a restrição vigente.
2. **Semente do quadro sob `GET /quadro`.** O quadro é criado de forma
   **idempotente** na primeira consulta. O modo leitura da licença bloqueia
   apenas escritas de negócio (POST/PATCH/DELETE), não a estrutura do quadro —
   a semente roda sob um GET e não altera dados de negócio.
3. **Nomes de timestamp.** As tabelas novas usam `criado_em`/`atualizado_em`
   (nomes do PRD §9), que **já são usados** no repositório (`MovimentoEstoque`,
   `UsuarioSessao`, Financeiro). `atualizado_em` usa `onupdate=func.now()`
   (precedente em `movimento.py`).
4. **`schema.sql` não foi estendido.** É um documento de referência da **Fase 0**
   e já está desatualizado (não contém `licenca`, da `v0.2.1`, nem
   `cliente_pagamento_adiantado`). As **migrações Alembic** são a fonte de
   verdade. Se você quiser o `schema.sql` regenerado/sincronizado, é um passo
   separado.
5. **Vínculo com a O.S. (RN2) fica na Fase 5.** As colunas `ordem_servico_id`
   (única) e `status_os` já existem para recebê-lo; mover um cartão **ainda não**
   sincroniza o status da O.S.
6. **`null` explícito limpa o campo (`PATCH /cartoes/{id}`).** Como o router usa
   `exclude_unset=True`, campo **ausente** = "não mexer" e campo presente com
   `null` = "limpar". Isso permite remover prazo/descrição/lembrete pela ficha do
   cartão (`titulo` continua obrigatório no schema). `atribuir_cartao` não tem
   "desatribuir": remover o acesso é feito removendo os membros.
7. **Índice no sinal `movido` do Kanban.** O componente genérico passou a emitir
   `(id, chave_destino, indice)` (antes `(id, chave)`); o menu de contexto envia
   `-1` (anexar ao final). Mudança interna — o `QuadroKanban` só é usado por esta
   tela.

---

## 7. Pendências (Fases 2–4 do PRD)

- **Fase 2:** etiquetas, checklists, comentários, atividade (auditoria), anexos
  (`capa_anexo_id` entra aqui), lembretes, filtros por etiqueta/prazo/membro.
- **Fase 3:** calendário, arquivados (UI), compartilhamento e "Gerar O.S." a
  partir do cartão.
- **Vínculo com O.S. (RN2)** e **"Aprovar e atribuir" (WF1)** — mapeamento
  lista ↔ status da O.S. e criação de O.S. a partir do cartão.
- **Sincronização entre estações (≤ 5 s).** A Fase 1 prevê o mecanismo: a
  visibilidade e as mutações já são server-side; falta o *polling*/SSE na tela.
  A `versao` otimista já evita sobrescrita em concorrência.
- **UI da Fase 2/3:** calendário e visão de **arquivados**, compartilhamento e
  "Gerar O.S.", além das etiquetas/checklists/comentários/anexos da Fase 2.

---

## 8. Como rodar

```powershell
# migração (dev)
cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head

# testes
cd backend; .\.venv\Scripts\python.exe -m pytest -q

# API
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
# documentação interativa: http://127.0.0.1:8000/docs  (tag "projetos")
```
