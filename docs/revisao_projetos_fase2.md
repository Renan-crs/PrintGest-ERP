# Projetos (Quadro Kanban) — Fase 2 (Cartão rico): backend

Documento de entrega da **Fase 2** do módulo **Projetos** descrito no
`PRD — Módulo Projetos (Quadro Kanban)` (v1.0.0), cujo modelo de dados já havia
entrado na migração `f2a3b4c5d6e7`. Esta entrega fecha o **backend**:
serviço, rotas e testes de **etiquetas, checklists, comentários e atividade**.

> **Escopo desta entrega.** Apenas o *backend* da Fase 2, sobre o mesmo
> namespace `/v1/projetos` (aditivo). **Anexos** e `capa_anexo_id` ficam para a
> Fase 3; **lembretes** e **filtros** por etiqueta/prazo/membro continuam em
> backlog. A tela do desktop e `/v1/os` não foram tocados.

---

## 1. Aditivo, sem quebrar o que existe

- nada mudou em `/v1/os`, `ordem_servico` ou no quadro da Fase 1;
- **nenhuma migração nova**: as tabelas já entraram em `f2a3b4c5d6e7`
  (`upgrade`/`downgrade` validados);
- o serviço da Fase 1 passou a **registrar atividade** nas escritas que já
  existiam (criar/editar/mover/arquivar/restaurar/atribuir/membros). É uma
  inserção em tabela nova — nenhum campo, cálculo ou código de resposta mudou;
- `CartaoOut` ganhou os campos que os schemas já declaravam (`etiquetas`,
  `checklist_total`, `checklist_concluidos`, `comentarios_total`), agora
  preenchidos em vez de ficarem nos valores padrão.

---

## 2. O que entrou

### Etiquetas (RF10)

- **Catálogo por filial**: `GET/POST /etiquetas`, `PATCH/DELETE /etiquetas/{id}`.
  Cor no formato `#RRGGBB`/`#AARRGGBB` (validada no schema), nome opcional.
- **Estrutura**: criar/editar/excluir é de **Admin/Gerente** (mesmo critério das
  listas do quadro); **Operador** lê o catálogo e aplica/remove.
- **No cartão**: `POST /cartoes/{id}/etiquetas` e
  `DELETE /cartoes/{id}/etiquetas/{etiqueta_id}`. Aplicar é **idempotente**
  (nem duplica nem gera log). Excluir a etiqueta derruba os vínculos por
  `ON DELETE CASCADE`.

### Checklists e itens (RF11)

- Vários por cartão: `GET/POST /cartoes/{id}/checklists`,
  `PATCH/DELETE /cartoes/{id}/checklists/{checklist_id}`.
- Itens: `POST /cartoes/{id}/checklists/{cid}/itens` e
  `PATCH/DELETE .../itens/{item_id}` — texto, `concluido`, responsável e
  `data_entrega`.
- **Ordenação fracionária** (mesmo motor da Fase 1): `posicao` recebe o índice
  0-based da API e rebalanceia quando o passo se esgota. Funciona para
  checklists (dentro do cartão) e itens (dentro do checklist).
- **Progresso do cartão**: `checklist_total` e `checklist_concluidos` (todos os
  itens de todos os checklists).

### Comentários (RF14)

- `GET/POST /cartoes/{id}/comentarios`,
  `PATCH/DELETE /cartoes/{id}/comentarios/{comentario_id}`.
- **Resposta em 1 nível**: `resposta_a_id` aponta para a raiz; responder a uma
  resposta devolve **400**.
- **Edição** apenas pelo autor (403 para os demais).
- **Soft-delete**: exclusão pelo autor; gestores (Admin/Gerente) **moderam**.
  A linha permanece, `texto` volta `null` e `excluido=true` — as respostas não
  se rompem.

### Atividade (RF14/§12)

- Log **append-only** em `cartao_atividade`, lido em
  `GET /cartoes/{id}/atividade` (mais recente primeiro, limite de 200).
- Tipos gravados: `criado`, `atualizado`, `movido`, `arquivado`, `restaurado`,
  `atribuido`, `membro_add`, `membro_remove`, `etiqueta_add`, `etiqueta_remove`,
  `checklist_criado`, `checklist_excluido`, `item_criado`, `item_concluido`,
  `item_reaberto`, `item_atualizado`, `item_excluido`, `comentario`,
  `comentario_excluido`.
- `dados` (JSONB) guarda o contexto: lista de origem/destino, campos alterados,
  ids de etiqueta/checklist/item, `texto` do item excluído etc.

---

## 3. Decisões (para revisão)

1. **Etiqueta é estrutura da filial.** Criar/editar/excluir exige Admin/Gerente,
  como no quadro; aplicar/remover é operação. Parte do pressuposto de que o
  catálogo é compartilhado — se virar "cada um cria a sua", muda o RBAC.
2. **Nenhuma escrita da Fase 2 incrementa `versao`.** A versão otimista existe
   para o `PATCH` do cartão, mover, arquivar e atribuir. Se etiquetas também
   incrementassem, aplicar uma etiqueta invalidaria a ficha aberta em outro
   cliente. Etiquetas, checklists e comentários são recursos próprios.
3. **Atividade é derivada da Fase 1 também.** O log registra os eventos do
   fluxo Fase 1 (criado/movido/…) porque foram adicionadas chamadas de
   `_registrar_atividade` no serviço existente. Custo: linhas em tabela nova;
   benefício: um log único e completo.
4. **Soft-delete de comentário.** Exclusão física quebraria `resposta_a_id`.
   O campo `excluido` esconde o texto e preserva o histórico.
5. **Invisível é 404, não 403.** Todas as sub-rotas entram por `_buscar_cartao`,
   herdando PV1–PV5: cartão restrito a outros membros devolve 404 também para
   checklists, comentários, etiquetas e atividade.
6. **Modo leitura** continua sendo bloqueio transversal por método HTTP
   (`POST/PATCH/DELETE` → `423`), sem whitelist por rota nova.

---

## 3.1. Fora do escopo (backlog)

- **Anexos** e `capa_anexo_id` → Fase 3;
- **Lembretes** de item e **filtros** por etiqueta/prazo/membro → backlog;
- **UI**: ficha do cartão com etiquetas/checklists/comentários e aba de
  atividade → próxima entrega da tela;
- **Anexo de arquivo** no comentário → Fase 3.

---

## 4. Testes

`backend/tests/test_projetos_fase2.py` — **17 testes**:

- etiquetas: RBAC (Operador × Gerente), cor inválida, atualização, aplicar/
  remover idempotente, etiqueta inexistente (404), exclusão limpa o vínculo;
- checklists: criação, itens com responsável, conclusão, progresso
  (`checklist_total`/`checklist_concluidos`), reordenação, item de checklist de
  **outro cartão** (404);
- comentários: resposta em 1 nível (400 ao aninhar), autoria na edição,
  soft-delete, moderação por gestor, `comentarios_total`;
- atividade: eventos de criação/etiqueta/checklist/item/comentário/mover, ordem
  (mais recente primeiro) e resolução do nome do autor;
- isolamento: cartão restrito a membros → 404 nas sub-rotas; **Caixa** sem
  acesso (403); **modo leitura** bloqueia escrita (423) e mantém o GET.

Suíte do backend: **167 testes** verdes (150 antes desta entrega).

---

## 5. Como rodar

```powershell
# migrações (já em head)
cd backend; .\.venv\Scripts\python.exe -m alembic upgrade head

# testes (backend)
cd backend; .\.venv\Scripts\python.exe -m pytest -q

# API
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
# documentação interativa: http://127.0.0.1:8000/docs  (tag "projetos")
```
