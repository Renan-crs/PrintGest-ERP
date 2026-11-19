# Fase 1 — Combobox de Cliente com Autocomplete em O.S./Orçamento

Implementado em 19/11/2026. **Sem mudança de contrato de API** — nenhuma
migration, nenhum campo novo no banco.

## Comportamento

1. **Estado inicial**: campo de texto livre (combobox editável).
2. **Ao digitar 2+ caracteres**: `QTimer` com debounce de 250 ms dispara
   `GET /v1/clientes?q=...&limit=20` em background (`tarefas.rodar`).
   Contador `_geracao` descarta respostas de buscas anteriores.
3. **Com correspondência**: primeira opção é selecionada automaticamente
   (`valor()` = `cliente_id`); o dropdown nativo do `QComboBox` navega com
   setas/Enter/Tab (PRD v3.3 §7). Ao selecionar, **Telefone** e **E-mail**
   são preenchidos automaticamente e o checkbox "Salvar como novo cliente"
   é desmarcado.
4. **Sem correspondência**: estado visual **"Nenhum cliente — salve como
   novo"** (via `estado_atencao`, ícone `•` + texto, não só cor); o operador
   preenche nome/telefone/e-mail e marca **"Salvar como novo cliente"**.
   No `F10`, o cliente é criado via `POST /v1/clientes` e o `id` retornado
   entra no payload da O.S. — a venda/orçamento nunca é perdida.
5. **Máscara de telefone**: `CampoTelefone` com formatação adaptativa
   `(00) 00000-0000` (fixo 10 ou celular 11 dígitos).

## Componente reutilizável

`CampoClienteAutocomplete` em `formulario.py`, com:
- `valor()` → `cliente_id`, `definir()`, `alterar_opcoes()` (compatível com o
  mixin `CondicaoPagamentoCliente`);
- `cliente_selecionado` → dict completo (telefone/e-mail);
- `sem_correspondencia` / `estado_mensagem` para a tela reagir;
- delegados `count/itemData/findData/...` para compatibilidade com código e
  testes legados que tratavam `widget` como `QComboBox`.

Aplicado em `PaginaOS` — `PaginaOrcamento` herda tudo (mesmo campo).

## Validação
- `tests/test_os.py`: busca remota com autopreenchimento, sem correspondência,
  e todos os testes anteriores de O.S. (31 + casos de layout).
- Desktop: **424 passed, 4 xfailed**.
- Evidência visual: `docs/evidencias/p3_1024x768/os_form_autocomplete_cliente.png`.

## Fase 2 — cliente avulso persistido (implementada)

- `ordem_servico.cliente_nome_avulso` (migration `a0b1c2d3e4f5`, aplicada no
  Neon em 19/11): permite `cliente_id = NULL` com nome livre.
- `OsCreate/OsUpdate/OsOut`: `cliente_id` é opcional; validação exige ao menos
  um de `cliente_id` / `cliente_nome_avulso` (nunca ambos).
- `os_service`: cria/atualiza com o nome avulso; `adiantamento_service` já
  trata `cliente=None` (sem exigência de sinal).
- **Conversão orçamento → O.S. preserva o nome avulso**.
- `GET /v1/os?q=` agora encontra O.S. com cliente avulso.
- Desktop: `_cliente_da_os()` resolve id ou nome livre (igual ao PDV); lista
  exibe `cliente_nome` ou `cliente_nome_avulso`.

A Fase 1 (criar cliente no ato do salvamento) continua disponível via o
checkbox "Salvar como novo cliente" — agora o operador pode **escolher** não
cadastrar, usando o avulso persistido.

## Validação Fase 2
`tests/test_os_cliente_avulso.py`: criar, validação, busca `q` e conversão.
Backend: **399 passed**. Desktop: **424 passed, 4 xfailed**.
