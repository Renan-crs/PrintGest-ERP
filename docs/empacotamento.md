# Empacotamento e instalador do PrintGest ERP

Como o sistema vira um pacote instalável em uma máquina sem Python, sem Git e
sem PostgreSQL pré-instalado: **um instalador único, com desinstalador**, que
na primeira execução prepara o banco local e pede o serial do RedGest antes do
login.

Tudo aqui é gerado por **um comando**:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
```

Saída: `dist_installer\PrintGest-Setup-<versão>.exe`.

---

## 1. Arquitetura da instalação

```
{localappdata}\Programs\PrintGest        (instalação por usuário, sem UAC)
├── PrintGest\PrintGest.exe              desktop PySide6 (PyInstaller onedir)
├── PrintGestAPI\
│   ├── PrintGestAPI.exe                  Local API Service (FastAPI + uvicorn)
│   ├── .env                              configuração da instalação
│   └── logs\printgest-api.log            log do serviço (sem console)
├── postgres\
│   ├── pgsql\                            binários PostgreSQL 16 (podados)
│   └── data\                            cluster — criado pelo initdb na 1ª execução
└── unins000.exe                          desinstalador (gerado pelo Inno Setup)
```

**Ciclo de vida**

1. O usuário abre `PrintGest.exe`.
2. O desktop sonda `http://127.0.0.1:8000/health`. Sem resposta, sobe o
   `PrintGestAPI.exe` irmão (desanexado, sem janela) e mostra a espera
   ("Preparando o banco de dados local...").
3. `PrintGestAPI.exe` na **primeira execução**: `initdb` do cluster em
   `postgres\data` → `pg_ctl start` (127.0.0.1, porta do `database_url`) →
   `CREATE DATABASE` → migrations Alembic (`upgrade head`) → uvicorn em
   `127.0.0.1:8000`. Nas seguintes: só conferir/start e servir.
4. Desktop segue o fluxo normal: **serial antes do login** (gate de
   instalação), login, dashboard.
5. Fechar o desktop **não** derruba o daemon — o Local API Service é um
   serviço local por desenho (PRD §3.1); a próxima abertura reaproveita o
   banco quente. A desinstalação encerra tudo.

## 2. Por que essas decisões

- **Instalação por usuário (`PrivilegesRequired=lowest`)**: o cluster do
  PostgreSQL é gravado dentro da pasta do app — em `Program Files` o usuário
  comum não teria permissão de escrita. Bônus: zero prompt de UAC.
- **`API_HOST=127.0.0.1`** no `.env` da instalação: evita o prompt do firewall
  do Windows na primeira execução e não expõe a API local.
- **`console=True` no daemon + `CREATE_NO_WINDOW` no desktop**: um exe
  PyInstaller *windowed* trava no startup — uvicorn/logging escrevem em um
  `sys.stderr` que não existe sem console. O desktop sobe o daemon com
  `CREATE_NO_WINDOW | DETACHED_PROCESS`, então o usuário nunca vê console;
  abrindo o `PrintGestAPI.exe` direto do Explorador ele aparece (útil para
  suporte).
- **`pg_ctl start` sem captura de saída**: o `postgres.exe` (processo neto,
  destacado) herda os handles de stdout do `pg_ctl` — com pipe, o
  `subprocess.run` espera um EOF que nunca chega e o daemon trava na primeira
  execução. O start roda com std em `DEVNULL` (o log do banco continua no
  `postgres.log` via `-l`).
- **PostgreSQL podado**: o zip de binários traz `pgAdmin 4` (~673 MB), `doc`,
  `include` e `StackBuilder`, que nada tem a ver com o runtime do servidor.
  O `empacotar.ps1` copia só `bin`, `lib` e `share` (sem `wx*.dll`/`ecpg`) —
  ~110 MB brutos, o resto fica fora.
- **Migrations no congelado**: um exe PyInstaller não tem `python -m alembic`.
  `app/core/migrations.py` detecta `sys.frozen` e roda `command.upgrade` da
  API Python, com `alembic.ini` + `alembic/` vindos de `sys._MEIPASS` (o
  `Config` é montado sem arquivo para o `env.py` não reconfigurar o logging
  da aplicação via `fileConfig`).- **`.env` ao lado do exe**: o pydantic resolve `env_file` pelo CWD, que num
  atalho do menu Iniciar não é a pasta do app. O `run_server.py` injeta o
  `.env` do diretório do executável no ambiente (variáveis reais continuam
  vencendo — útil para diagnóstico).

## 3. O que o `.env` da instalação carrega

Gerado pelo `empacotar.ps1` a partir de `backend\.env`, com três chaves
forçadas:

```env
PRINTGEST_PG_EMBARCADO=true     # daemon prepara o cluster na 1ª execução
PRINTGEST_API_HOST=127.0.0.1    # sem firewall prompt / sem exposição
PRINTGEST_ENV=local             # passa na checagem anti-defaults (P17)
```

O restante (URL/`api_key` do RedGest, contrato, `DATABASE_URL`) vem do
`.env` de dev. **Atenção**: isso inclui a `api_key` do sistema no RedGest —
o pacote é para piloto interno; para distribuição externa, mover a credencial
para uma fonte por cliente (ou emissão individual por instalação).

## 4. Desinstalador

O `unins000.exe` (Inno Setup) roda as etapas de `[UninstallRun]` **antes** de
apagar arquivos:

1. `taskkill` do `PrintGest.exe` e do `PrintGestAPI.exe`;
2. `pg_ctl stop -m fast` do cluster embarcado;
3. remoção de `postgres\data`, `logs` e `postgres.log` (`[UninstallDelete]`).

Os **dados saem junto com o app** — o cluster local é da instalação. Quem
precisa conservar dados entre reinstalações deve exportar (ou replicar o
diretório `postgres\data`) antes.

## 5. Diagnóstico na máquina do cliente

| Sintoma | Onde olhar |
| --- | --- |
| Tela de serial não aparece | `GET /health` responde? `PrintGestAPI\logs\printgest-api.log` |
| "Local API Service indisponível" | daemon não subiu: log acima + `.env` presente? |
| Primeira execução demora | normal (initdb); passou de ~1 min, ver `postgres\postgres.log` |
| Ativação falha | contrato no `.env` (`c`/`b`) + resposta do RedGest no log |
| Reinstalar do zero | desinstalar (remove o cluster) → instalar → serial de novo |

Variáveis de emergência (setadas no processo, vencem o `.env`):
`PRINTGEST_API_PORT`, `PRINTGEST_DATABASE_URL`, `PRINTGEST_LICENCA_DESABILITADA`.

## 6. Requisitos de build (máquina de desenvolvimento)

- `backend\.venv` e `desktop\.venv` com `pip install pyinstaller`;
- PostgreSQL de dev extraído em `.dev\postgres\pgsql`
  (`scripts\setup_postgres.ps1` — o empacotar só lê os binários);
- Inno Setup 6 (`winget install JRSoftware.InnoSetup` — o script usa o ISCC
  per-user em `%LOCALAPPDATA%\Programs\Inno Setup 6`).

## 7. Roadmap

- [ ] Assinatura digital do instalador e dos exes (evita SmartScreen).
- [ ] Atualização in-place (detector de versão + download incremental).
- [ ] Backup/restauração do cluster via interface (hoje: cópia do `data`).
- [ ] Serviço do Windows opcional para o daemon (auto-start no boot).

## 8. Validação executada (24/10/2026, máquina de dev)

Instalação silenciosa em pasta de teste + primeira execução **fria** (cluster
zerado), sem tocar nos serviços de dev (PostgreSQL de dev em 5432 e daemon de
dev em 8000 — o teste usou 5433/8010 via variáveis de ambiente):

| Verificação | Resultado |
| --- | --- |
| `PrintGest-Setup-0.2.2.exe /VERYSILENT` | layout completo (2 exes, PG, `.env`, `unins000.exe`) |
| Primeira execução do `PrintGestAPI.exe` | initdb → start → createdb → migrations (head `d7a1c4e8b2f3`, 37 tabelas) → bootstrap → uvicorn em **19,9 s** |
| `GET /health` / `GET /v1/licenca` | 200 / `nao_ativada` (gate de serial antes do login) |
| Log em arquivo (`logs/printgest-api.log`) | migrations e requisições registradas |
| Segunda execução (cluster quente) | servindo em **4,5 s** |
| Desinstalação (`unins000.exe /VERYSILENT`) | daemon encerrado, PostgreSQL parado, app/atalhos/registro removidos |

Bugs achados e corrigidos nessa bateria: exe windowed travava no startup
(uvicorn/logging sem stderr) → daemon agora é `console=True` lançado com
`CREATE_NO_WINDOW`; `pg_ctl start` com `capture_output` deadlockava (pipe
herdado pelo postgres) → start com std em `DEVNULL`; raiz do PostgreSQL
congelada apontava para dentro da pasta do exe → correção para a pasta irmã
(três testes de regressão).
