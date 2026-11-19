# Verificação das chamadas API ↔ endpoints — Orçamento

Verificado em 19/11/2026. Abrangência: botões da tela, chamadas API, payload
de salvamento, conversão em O.S. e gravação no banco ( Neon + banco isolado de
testes ).

## Contrato conferido — consistente

| Tela (desktop) | API desktop | Endpoint backend | Status |
|---|---|---|---|
| `PaginaOrcamento` (`TIPO="orcamento"`) | `listar_os(tipo=...)` | `GET /v1/os?tipo=orcamento` | ✅ |
| Selecionar linha | (objeto da própria lista) | — | ✅ |
| **Salvar** (F10) | `criar("os", payload)` / `atualizar("os", id, payload)` | `POST /v1/os` / `PUT /v1/os/{id}` | ✅ |
| **Converter em O.S.** (F9) | `acao("os", id, "converter", {pagamento_confirmado})` | `POST /v1/os/{id}/converter` | ✅ |
| **Cancelar Orçamento** (F8, em "Mais ações") | `excluir("os", id)` | `DELETE /v1/os/{id}` → 204 | ✅ |
| **Cotações** (em "Mais ações") | `listar/lançar/selecionar_cotacao` | `GET|POST /v1/os/{id}/itens/{item}/cotacoes`, `PUT .../{cot}/selecionar` | ✅ (GERENTE+) |
| Cliente/Funcionários/Produtos | `listar("pdv/...")`, autocomplete | espelhos de leitura CAIXA-safe | ✅ |
| Novo cliente inline | `criar("clientes", ...)` | `POST /v1/clientes` | ✅ |

- `tipo="orcamento"` casa com `TipoOs.ORCAMENTO` (StrEnum, mesmo valor).
- `OsCreate` aceita `tipo`; `OsConverterIn.pagamento_confirmado` casa com o
  corpo enviado; `DELETE` cancela logicamente (`status=cancelado`).
- Filtros `aberto/convertido/cancelado` existem no enum `status_os`.
- Não existe rota `/v1/orcamento` — orçamento é sempre `/v1/os` com `tipo`.

## Bugs encontrados e corrigidos

### 1. 🔴 PUT apagava cotações, snapshot e rastreio de terceirizado
A UI reenvia a lista inteira de itens; `OsItemIn` não tinha `id` e
`os_service.atualizar` fazia `os_obj.itens = _montar_itens(...)`, disparando
`delete-orphan`. Salvar qualquer alteração em um orçamento cotado apagava as
cotações e o `snapshot_preco`, e a conversão em O.S. falhava depois com **409
"sem cotação selecionada"**.

Correção: `OsItemIn.id` + mesclagem por `id` em `_mesclar_itens`
(atualiza no lugar, preserva `snapshot_preco`/`cotacoes`/`executado`/
`OsTerceirizado`; itens novos sem id são criados; removidos saem pelo cascade).
Seq temporário negativo evita violação transitória da UNIQUE `(os_id, seq)`.

Teste: `backend/tests/test_orcamento_persistencia.py` (3 casos) — after PUT o
item mantém id, `estado_cotacao=cotado`, snapshot/terceirizado intactos e a
conversão retorna 200.

### 2. 🔴 Editar cliente avulso trocava o nome por um cliente cadastrado
`CampoClienteAutocomplete` repovoava o combo e auto-selecionava o primeiro
cliente; o PUT transformava o avulso em outro cadastro. Corrigido em três
camadas: `setEditText` com sinais bloqueados ao preencher, autoseleção apenas
quando o termo é prefixo do nome encontrado, e `_cliente_da_os()` só aceita
`cliente_id` quando o texto confere com o rótulo da opção selecionada.

### 3. 🟠 Formas de pagamento divergentes do banco
O pacote `printgest.core.dominio` (que sombreia `dominio.py`) exportava
`transferencia/cheque/outro` — valores **inexistentes** no enum do Postgres —
e não tinha `fiado`. Selecionar qualquer um deles gerava 422. Fonte única
corrigida; `FORMAS_PAGAMENTO_LABEL` agora é derivada da lista.

### 4. 🟠 `_api.usuario()` chamado como método
`Api.usuario` é `@property` (dict). O `TypeError` era engolido e os padrões de
vendedor/atendente do usuário nunca eram aplicados. Corrigido para
`getattr(self._api, "usuario", None)`.

### 5. 🟡 Erros 422 ilegíveis
`_detalhe()` exibia o `repr` da lista de erros do Pydantic. Agora extrai as
mensagens e os campos (`"cliente_nome_avulso: Field required · ..."`).

### 6. 🟡 Cosméticos
Tooltip de "Salvar" agora diz "orçamento" na tela de orçamento; dica duplicada
de F10 em "Cotações" removida. OsUpdate agora valida cliente/avulso (antes só
`OsCreate` validava).

## Persistência verificada

- Banco isolado de testes (`printgest_test`): criação, listagem filtrada, PUT
  com merge, conversão e cancelamento — 407 testes backend verdes.
- Neon (produção, somente leitura via MCP): head Alembic `a0b1c2d3e4f5`
  (nenhuma migration nova nesta versão), 4 orçamentos gravados, enum
  `forma_pagamento` = `dinheiro, cartao_credito, cartao_debito, pix, boleto,
  fiado` — confere com a lista corrigida do desktop. Nenhuma alteração de
  schema foi necessária.

## Ressalvas (não divergência de contrato)

- `valor_sinal` continua informativo em orçamento: `adiantamento_service` calcula
  a exigência pelos flags do cliente, e a conversão copia o campo. Não gera
  conta a receber por si só (comportamento atual do produto).
- `os_service` não emite evento de sync outbox nem kardex (ao contrário de
  `venda_service`). Se a política passar a exigir replicação de OS/orçamento,
  é uma mudança de arquitetura — não feita aqui.

## Validação
Backend: **407 passed**. Desktop: **436 passed, 4 xfailed**.
