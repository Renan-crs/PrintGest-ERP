# Empacota o PrintGest ERP em um instalador único (Inno Setup) com desinstalador.
#
# Etapas:
#   1. PrintGestAPI.exe  - backend FastAPI/uvicorn (PyInstaller onedir)
#   2. PrintGest.exe     - desktop PySide6 (PyInstaller onedir)
#   3. PostgreSQL 16     - binários podados (sem pgAdmin/doc/include)
#   4. .env da instalação - gerado a partir de backend\.env + chaves da máquina
#   5. PrintGest-Setup-<versao>.exe - instalador Inno Setup (unins000.exe incluso)
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
#
# Requisitos: venvs de backend/desktop com PyInstaller (pip install pyinstaller)
# e Inno Setup 6 (ISCC em %LOCALAPPDATA%\Programs\Inno Setup 6).

$ErrorActionPreference = "Stop"

$raiz      = Split-Path -Parent $PSScriptRoot
$build     = Join-Path $raiz "build"
$dist      = Join-Path $build "dist"
$pacote    = Join-Path $build "pacote"
$installer = Join-Path $raiz "installer"
$pyApi     = Join-Path $raiz "backend\.venv\Scripts\pyinstaller.exe"
$pyDesktop = Join-Path $raiz "desktop\.venv\Scripts\pyinstaller.exe"
$iscc      = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

foreach ($ferramenta in @($pyApi, $pyDesktop, $iscc)) {
    if (-not (Test-Path $ferramenta)) {
        throw "Ferramenta não encontrada: $ferramenta"
    }
}

# Versão do pacote sai do próprio desktop (fonte única da verdade).
$versao = (Select-String -Path (Join-Path $raiz "desktop\printgest\__init__.py") `
    -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "== PrintGest ERP $versao =="

# ------------------------------------------------------------ 1) limpeza
foreach ($alvo in @((Join-Path $dist "PrintGest"), (Join-Path $dist "PrintGestAPI"), (Join-Path $pacote "postgres"))) {
    if (Test-Path $alvo) { Remove-Item -Recurse -Force $alvo }
}

# --------------------------------------------------- 2) backend (PrintGestAPI)
Write-Host "[1/5] PyInstaller: PrintGestAPI.exe (backend)..."
Push-Location $installer
try {
    & $pyApi "printgestapi.spec" --clean --noconfirm --distpath (Join-Path $dist "") --workpath (Join-Path $build "work_api")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou no backend." }
} finally { Pop-Location }

# ---------------------------------------------------- 3) desktop (PrintGest)
Write-Host "[2/5] PyInstaller: PrintGest.exe (desktop)..."
Push-Location $installer
try {
    & $pyDesktop "printgest.spec" --clean --noconfirm --distpath (Join-Path $dist "") --workpath (Join-Path $build "work_desktop")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou no desktop." }
} finally { Pop-Location }

# ------------------------------------------- 4) PostgreSQL embarcado (podado)
Write-Host "[3/5] PostgreSQL embarcado (bin, lib, share)..."
$pgOrigem = Join-Path $raiz ".dev\postgres\pgsql"
$pgDestino = Join-Path $pacote "postgres\pgsql"
if (-not (Test-Path (Join-Path $pgOrigem "bin\pg_ctl.exe"))) {
    throw "PostgreSQL de dev não encontrado em $pgOrigem (rode scripts\setup_postgres.ps1)."
}
# pgAdmin 4 (~673 MB), doc, include e StackBuilder não são usados em runtime;
# wx*.dll/ecpg pertencem a ferramentas fora do fluxo servidor.
robocopy $pgOrigem $pgDestino /E /NFL /NDL /NJH /NJS /NP `
    /XD "pgAdmin 4" "doc" "include" "StackBuilder" "symbols" `
    /XF "wx*.dll" "ecpg.exe" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy do PostgreSQL falhou (código $LASTEXITCODE)." }
$LASTEXITCODE = 0

# ------------------------------------------------------ 5) .env da instalação
Write-Host "[4/5] Gerando o .env da instalação..."
$envOrigem = Join-Path $raiz "backend\.env"
if (-not (Test-Path $envOrigem)) { throw "backend\.env não encontrado." }
# Chaves fixas da instalação empacotada (as demais vêm do .env de dev):
#   PG_EMBARCADO  -> o daemon prepara o cluster na primeira execução
#   API_HOST      -> 127.0.0.1: sem prompt de firewall, sem expor a API
#   ENV           -> "local" passa na checagem anti-defaults de produção
$forcadas = @{
    "PRINTGEST_PG_EMBARCADO" = "true"
    "PRINTGEST_API_HOST"     = "127.0.0.1"
    "PRINTGEST_ENV"          = "local"
}
$linhas = Get-Content $envOrigem | Where-Object {
    $_ -notmatch '^\s*PRINTGEST_(PG_EMBARCADO|API_HOST|ENV)\s*='
}
$conteudo = @($linhas) + @(
    "",
    "# Instalação empacotada (gerado por scripts/empacotar.ps1)"
) + @($forcadas.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" })
$conteudo | Set-Content -Path (Join-Path $dist "PrintGestAPI\.env") -Encoding utf8

# ------------------------------------------------------------- 6) LEIA-ME
$leiaMe = @"
PrintGest ERP $versao

PRIMEIRA EXECUCAO
  1. Abra o PrintGest ERP (atalho da area de trabalho / menu Iniciar).
  2. O sistema prepara o banco de dados local (leva alguns segundos).
  3. A tela de ativacao pede a licenca emitida pelo RedGest - como em
     programas licenciados por serial, ela so e pedida na instalacao.
  4. Faca login com o usuario inicial: admin / admin123 (troque a senha
     no primeiro acesso, em Configuracao > Usuarios e Niveis).

ONDE FICAM AS COISAS
  - Programa:        {localappdata}\Programs\PrintGest
  - Banco de dados:  ...\PrintGest\postgres\data (PostgreSQL embarcado)
  - Log do servico:  ...\PrintGest\PrintGestAPI\logs\printgest-api.log

DESINSTALACAO
  Use "Desinstalar PrintGest ERP" no menu Iniciar ou Aplicativos do Windows.
  A desinstalacao encerra o servico, para o PostgreSQL embarcado e remove o
  banco local. Os dados do sistema saem junto - exporte antes, se precisar.

Suporte: veja docs/empacotamento.md no repositorio.
"@
$leiaMe | Set-Content -Path (Join-Path $pacote "LEIA-ME.txt") -Encoding utf8

# --------------------------------------------------- 7) instalador Inno Setup
Write-Host "[5/5] Compilando o instalador Inno Setup..."
$saida = Join-Path $raiz "dist_installer"
if (-not (Test-Path $saida)) { New-Item -ItemType Directory -Force -Path $saida | Out-Null }
& $iscc "/O$saida" "/DVersaoApp=$versao" (Join-Path $installer "PrintGest.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$setup = Join-Path $saida "PrintGest-Setup-$versao.exe"
$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "OK: $setup ($mb MB)"
Write-Host "Instale em outra maquina: execucao dupla, sem UAC (instalacao por usuario)."
