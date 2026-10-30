# Empacotamento e instalador do PrintGest ERP

Como o sistema vira um pacote instalável em uma máquina sem Python, sem Git e
sem PostgreSQL pré-instalado: **instaladores únicos, com desinstalador** — no
**modo Servidor** (desktop + Local API Service + PostgreSQL embarcado) e no
**modo Estação** (só o desktop, conectando ao servidor da gráfica).

> **M0/PRD v3.0:** o PDV agora exige **caixa aberto** para o vendedor logado
> (`409 "Caixa fechado"` no servidor + banner na tela). Primeira coisa a fazer
> em uma instalação nova: Financeiro → **Caixa** → *Abrir caixa*.

Tudo aqui é gerado por **um comando**:

```powershell
# Servidor (máquina que guarda banco e licença)
powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1

# Estação (usa o servidor da gráfica)
powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1 -Modo estacao
```

Saídas: `dist_installer\PrintGest-Setup-<versão>.exe` (Servidor) e
`PrintGest-Setup-<versão>Estacao.exe` (Estação). Os dois convivem na mesma
máquina (AppIds e pastas distintas).

---

## 1. Arquitetura da instalação

### Modo Servidor (a máquina que guarda banco e licença)

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

### Modo Estação (usa o servidor da gráfica)

```
{localappdata}\Programs\PrintGestEstacao
├── PrintGest\
│   ├── PrintGest.exe
│   └── .env                              PRINTGEST_API_URL=<servidor> + MODO_ESTACAO=sim
└── unins000.exe
```

Sem backend e sem PostgreSQL: o assistente de instalação **pergunta o endereço
do servidor** (ex.: `192.168.0.10:8000`) e grava no `.env` ao lado do exe — o
desktop lê esse arquivo ao iniciar (`main._carregar_env_do_executavel`).
Instalação silenciona usa endereço vazio e o usuário informa na tela
**Conectar ao Servidor** (D6). O gate de serial não existe na estação: a
licença pertence ao servidor, que aplica o modo de leitura quando algo não
está em ordem.

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

- **Ícones do produto**: `ui/assets/printgest.ico` (16–256 px, gerado de
  `printgest-icone.svg` por `desktop/tools/gerar_ico.py` — Qt rasteriza,
  Pillow empacota) vai no exe (PyInstaller `icon=`), no Setup e na
  desinstalação (Inno `SetupIconFile`/`UninstallDisplayIcon`) e na taskbar
  (`app.setWindowIcon`). Regenerar quando o logo mudar.
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
  da aplicação via `fileConfig`).
- **`.env` ao lado do exe**: o pydantic resolve `env_file` pelo CWD, que num
  atalho do menu Iniciar não é a pasta do app. O `run_server.py` injeta o
  `.env` do diretório do executável no ambiente (variáveis reais continuam
  vencendo — útil para diagnóstico).

## 3. O que o `.env` da instalação carrega

Gerado pelo `empacotar.ps1` a partir de **`installer/env.instalacao`** (quando
existe — credenciais por cliente, fora do git) ou do template versionado
**`installer/env.instalacao.example`**. **O `backend\.env` de dev não é lido**:
o pacote nunca herda segredos do ambiente de desenvolvimento.

Três chaves são sempre impostas pelo build:

```env
PRINTGEST_PG_EMBARCADO=true     # daemon prepara o cluster na 1ª execução
PRINTGEST_API_HOST=127.0.0.1    # sem firewall prompt / sem exposição
PRINTGEST_ENV=local             # passa na checagem anti-defaults (P17)
```

**Credencial RedGest (`api_key`)** — por padrão o pacote **não** carrega
nenhuma:

- **Contrato B** (CNPJ + código): o handshake não usa `api_key` — o pacote
  sai limpo. As credenciais M2M vêm da ativação e ficam no cofre do SO
  (DPAPI) da máquina do cliente.
- **Contrato C** (chave de produto): a validação é assinada com a
  `api_key` do Sistema — preencha em `installer/env.instalacao` (ignorado
  pelo git). **O build recusa `CONTRATO=c` com a chave vazia** para nunca
  embarcar um pacote que não ativa.

Quem distribui o mesmo Setup para N clientes com Contrato C embute a mesma
credencial em todos — avaliar emissão individual ou proxy por cliente antes
de distribuir externamente.

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

## 7. Assinatura digital e SmartScreen

Um Setup sem assinatura dispara o **SmartScreen** ("O Windows protegeu o
computador") na primeira máquina que o executa — quem instala clica em "Mais
informações → Executar assim mesmo". Para o piloto interno isso é aceitável;
para cliente, só o certificado resolve.

O pipeline já está pronto: `signtool` do Windows SDK é detectado
automaticamente e assina **os dois exes antes de virarem Setup** e o próprio
Setup depois, com carimbo de tempo (timestamp):

```powershell
# thumbprint do certificado em Cert:\CurrentUser\My
powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1 -Assinar <THUMBPRINT>

# ou um arquivo .pfx (senha na variável PRINTGEST_SIGN_SENHA)
powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1 -Assinar C:\cert\printgest.pfx
```

### Auto-assinatura (Gratuita, para testes)

Para testes internos ou ambientes controlados, use o script de auto-assinatura:

```powershell
# Cria certificado + empacota com assinatura auto-assinada
powershell -ExecutionPolicy Bypass -File scripts\empacotar_autosign.ps1
```

**Resultado:** O instalador terá assinatura, mas o SmartScreen ainda pode mostrar
aviso (limitação do auto-assinado). Útil para:
- Testes internos
- Ambientes de teste controlados
- Distribuição limitada com aviso claro

### Certificado de Code Signing Real

Para eliminar completamente o SmartScreen, adquira um certificado:

| Opção | Custo aprox. | Observação |
| --- | --- | --- |
| **Azure Trusted Signing** (Microsoft) | US$ 9,99/mês | individuais e empresas; exige `AzureSignTool` |
| Certum / SSL.com / GlobalSign (OV) | ~US$ 70–250/ano | `signtool` clássico, pronto no script |
| Certificado autoassinado (PowerShell) | grátis | **não resolve** o SmartScreen — só prova integridade |

SmartScreen limpa com reputação: nos primeiros downloads de um exe recém
assinado ainda pode aparecer o aviso azul até o arquivo acumular reputação
(certificados EV pulam essa fila).

## 8. Roadmap

- [x] Assinatura digital no pipeline (`-Assinar` + `signtool`)
- [x] Script de auto-assinatura (`scripts/empacotar_autosign.ps1`)
- [ ] Certificado de code signing real (Azure Trusted Signing ou OV).
- [ ] Atualização in-place (detector de versão + download incremental).
- [ ] Backup/restauração do cluster via interface (hoje: cópia do `data`).
- [ ] Serviço do Windows opcional para o daemon (auto-start no boot).

## 9. Validação executada (30/10/2026, máquina de dev)

Instalação silenciosa em pasta de teste + primeira execução **fria** (cluster
zerado), sem tocar nos serviços de dev (PostgreSQL de dev em 5432 e daemon de
dev em 8000 — o teste usou 5433/8010 via variáveis de ambiente). Validação
repetida após a mudança do `.env` para o template sem segredos:

| Verificação | Resultado |
| --- | --- |
| `PrintGest-Setup-0.2.2.exe /VERYSILENT` | layout completo (2 exes, PG, `.env`, `unins000.exe`) |
| `.env` instalado | template público, **sem `api_key`** (Contrato B não usa) |
| Contrato C sem `api_key` | build **recusa em 2 s** (fail-fast, antes de qualquer PyInstaller) |
| Primeira execução do `PrintGestAPI.exe` | initdb → start → createdb → migrations (head `d7a1c4e8b2f3`, 37 tabelas) → bootstrap → uvicorn em **18,2 s** |
| `GET /health` / `GET /v1/licenca` | 200 / `nao_ativada` com `contrato: b` (gate de serial antes do login) |
| Log em arquivo (`logs/printgest-api.log`) | migrations e requisições registradas |
| Segunda execução (cluster quente) | servindo em **4,5 s** |
| Desinstalação (`unins000.exe /VERYSILENT`) | daemon encerrado, PostgreSQL parado, app/atalhos/registro removidos |
| Ambiente de dev após a bateria | backend :8000 e PostgreSQL :5432 no ar e saudáveis |

Bugs achados e corrigidos nessa bateria: exe windowed travava no startup
(uvicorn/logging sem stderr) → daemon agora é `console=True` lançado com
`CREATE_NO_WINDOW`; `pg_ctl start` com `capture_output` deadlockava (pipe
herdado pelo postgres) → start com std em `DEVNULL`; raiz do PostgreSQL
congelada apontava para dentro da pasta do exe → correção para a pasta irmã
(três testes de regressão).
