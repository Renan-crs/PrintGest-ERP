# Viabilidade de execução silenciosa do console

Auditada em 20/11/2026. Veredito: **o daemon já é silencioso no fluxo normal**;
tornar o próprio binário *windowed* é viável após o endurecimento de logging
feito na v0.5.24.

## Como o daemon nasce hoje

`desktop/printgest/core/daemon.py:97-105`:

```python
subprocess.Popen(
    [str(caminho)],
    cwd=str(caminho.parent),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    close_fds=True,
)
```

Ou seja: **nenhuma janela de console aparece** quando o desktop inicia o
serviço. `PrintGestAPI.exe` abre com console apenas se o usuário der duplo
clique direto no Explorador — comportamento mantido de propósito para suporte
(`installer/printgestapi.spec:11-14`).

## Por que `console=True` no spec

`installer/printgestapi.spec:77`. O comentário original alertava que um exe
PyInstaller *windowed* podia travar no startup porque uvicorn/logging escrevem
em `sys.stderr` inexistente. A ordem antiga era:

1. `logging.basicConfig()` → cria `StreamHandler` para stderr;
2. `import app.main` → cria outro `StreamHandler` se não houver handlers;
3. só depois `_anexar_log_em_arquivo()`.

## Endurecimento aplicado (v0.5.24)

`backend/run_server.py`:

- `_garantir_streams()` substitui `sys.stdout`/`sys.stderr` nulos por `os.devnull`;
- `_anexar_log_em_arquivo()` passa a usar **`RotatingFileHandler`** (5 MB × 3),
  chamado **antes** de `basicConfig()` e do `import app.main` — com handler de
  arquivo já presente, `basicConfig()` não cria `StreamHandler`;
- `app/main.py::_configurar_logging()` usa `sys.stderr or open(os.devnull, "w")`.

`licensa_service.py` (PowerShell de hardware) e `backup_service.py`
(`pg_dump`) agora passam `CREATE_NO_WINDOW`, eliminando flashes de janelas
filhas.

## Alternativas avaliadas

| Alternativa | Viabilidade | Risco |
|---|---|---|
| Manter `console=True` + `CREATE_NO_WINDOW` (atual) | ✅ Recomendado | Nenhum; console só no lançamento manual |
| Trocar spec para `console=False` | ✅ Agora viável | Perde traceback visível no suporte; exige smoke test em instalação limpa |
| `pythonw.exe` | ❌ | Não se aplica ao bootloader do PyInstaller |
| Serviço do Windows | ❌ | Quebra zero-UAC, `{localappdata}`, cofre DPAPI por usuário e a regra `taskkill` do instalador |
| Tarefa agendada oculta no logon | ⚠️ | Viável como opcional; não roda sem logon e exige `[Code]` no Inno |
| `START_NEW_GROUP` | desnecessário | `DETACHED_PROCESS` já isola; nunca usar `CREATE_NEW_CONSOLE` |

## O que NÃO muda

- `taskkill /IM PrintGestAPI.exe /F` (regra de atualização) funciona por nome
  de imagem, com ou sem console.
- Tela de diagnóstico é 100% HTTP/JSON (`GET /v1/plataforma/diagnostico`) —
  não lê console.
- Fechamento automático das 23:00 é um loop `asyncio` no lifespan.
- Modo estação não inicia daemon algum.
- O antigo `GET /v1/atualizacao/verificar` era código morto; foi substituído
  na v0.5.35 pelo manifesto `latest.json` da release (ver
  `docs/atualizacao_notificacao.md`). A rota continua sem existir no backend.

## Lacunas que ainda existem

- Não há watchdog: o `QTimer` de 30 s só pinta "online/offline"; se o daemon
  morrer após o boot, é preciso reabrir o desktop.
- `daemon._porta_aberta()` considera saudável qualquer processo na porta 8000
  (falso positivo).
- Nenhum smoke test de exe congelado windowed.

## Decisão

Manter `console=True` no spec (suporte) e a execução silenciosa via
`CREATE_NO_WINDOW` no desktop. O endurecimento de logging remove o risco que
impedia a migração futura para `console=False`, sem mudar o comportamento
atual. Se precisar eliminar até o console do duplo-clique, basta trocar
`console=True` → `console=False` em `printgestapi.spec` e rodar o smoke test
de instalação limpa (`/VERYSILENT` + `/health` + log).
