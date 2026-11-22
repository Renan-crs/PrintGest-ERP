# Log detalhado de erros

Implementado em 22/11/2026. Requisito: **sempre que houver um erro, ele deve
ser detalhado no log** — com contexto e sem credenciais.

## Backend

Todos os erros HTTP passam por handlers centralizados em `app/main.py`:

| Erro | Handler | Linha típica no log |
|---|---|---|
| 400/401/403/404/409/503 (`HTTPException`) | `_erro_http` | `HTTP 409 POST /v1/... \| filial=1 usuario=1 tipo=HTTPException detail=...` |
| 422 (Pydantic) | `_erro_validacao` | `HTTP 422 POST /v1/... \| ... tipo=RequestValidationError detail=[campos]` |
| 500 (não tratada) | `_erro_nao_tratado` | `HTTP 500 ... tipo=RuntimeError erro=...` + **traceback** |
| 423 (modo leitura) | middleware `controle_modo_leitura` | `HTTP 423 ... motivo=modo_leitura estado=...` |
| 403 (módulo do plano) | `gating.controle_modulos` | `HTTP 403 ... modulo=... motivo=plano` |

- Os handlers incluem `exc_info` quando há traceback — exceções convertidas em
  `HTTPException` (`raise ... from exc`) gravam a cadeia completa.
- `deps.py` preenche ContextVars com **filial/usuário** para os handlers.
- `X-Request-ID` é preservado em **todos** os handlers (console e arquivo).
- `app/core/log_seguranca.py` é a fonte única de máscaras: `Bearer`, `token=`,
  `api_key`, `senha`, URLs `postgresql://user:pass@host`, chaves
  `XXXX-XXXX-XXXX-XXXX`, `sk_/rk_`. `FiltroSeguranca` aplica a máscara a
  mensagem, argumentos e traceback formatado.
- `fiscal_service` reutiliza as mesmas funções para a auditoria fiscal.

### Configuração

| Variável | Padrão | Finalidade |
|---|---|---|
| `PRINTGEST_LOG_NIVEL` | `INFO` | nível do root logger |
| `PRINTGEST_LOG_ARQUIVO` | `logs/printgest-api.log` | arquivo rotativo |
| `PRINTGEST_LOG_MAX_MB` | `5` | tamanho máximo por arquivo |
| `PRINTGEST_LOG_BACKUPS` | `3` | número de rotações |

Arquivo rotativo existe em **todo** ambiente (dev e exe congelado). No exe,
`run_server.py` cria o handler antes do `basicConfig()` para não depender de
`stderr` (binário `console=False`). `_configurar_logging()` é idempotente.

## Desktop

- `core/logging_app.py`: `configurar_logging()` cria
  `logs/printgest.log` (ao lado do exe, ou `%LOCALAPPDATA%\PrintGest\logs` em
  dev), rotação 5 MB × 3, filtro de sanitização.
- `main.py` chama `configurar_logging()` **antes** do `QApplication` e
  `sys.excepthook = _erro_inesperado`; `excepthook` grava tipo, mensagem
  mascarada e traceback.
- `core/tarefas.py::_Worker._executar` grava tipo, status e traceback antes de
  entregar o erro ao callback da UI.
- `core/api.py` grava `API HTTP <status> <método> <path> | detail=<mascarado>`
  em `_tratar`, `_resposta_completa`, `_delete` e `eventos_integracao`.

## Testes

- `backend/tests/test_logging_erros.py`: 404/422/409/400 logados, 500 com
  traceback e sanitização de segredos.
- `desktop/tests/test_logging_erros.py`: arquivo rotativo, traceback do worker,
  `ApiError` com detail mascarado e `excepthook`.
- Harness de mutação: **17/17 mortos** (inclui "log HTTP desligado" e
  "sanitização desligada").

**Suítes:** backend 455 passed; desktop 475 passed, 4 xfailed.
