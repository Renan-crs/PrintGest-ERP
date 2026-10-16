#scripts Postgres MGR portable (desenvolvimento)
# Baixa binários zip do PostgreSQL (uma vez), inicializa data dir e sobe o serviço
# na porta 5432, restrigido a 127.0.0.1 (as estações acessam via Local API Service).
<#
.SYNOPSIS
  Bootstraps PostgreSQL portable under .dev/postgres (phase 1 / embedded pg strategy).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/setup_postgres.ps1
#>

$ErrorActionPreference = "Stop"

$root    = Split-Path -Parent $PSScriptRoot
$dev     = Join-Path $root ".dev"
$pgDir   = Join-Path $dev "postgres"
$dist    = Join-Path $pgDir "_dist"
$dataDir = Join-Path $pgDir "data"
$logFile = Join-Path $pgDir "postgres.log"

$version   = "16.10"
$zipUrl    = "https://get.enterprisedb.com/postgresql/postgresql-$version-1-windows-x64-binaries.zip"
$zipPath   = Join-Path $dist "postgresql.zip"
$binDir    = Join-Path $pgDir "pgsql\bin"
$pgctl     = Join-Path $binDir "pg_ctl.exe"
$initdb    = Join-Path $binDir "initdb.exe"
$port      = 5432
$superUser = "printgest"

New-Item -ItemType Directory -Force -Path $dist | Out-Null

if (-not (Test-Path $pgctl)) {
    Write-Host "[1/4] Baixando PostgreSQL $version (~320MB)..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Write-Host "[2/4] Extraindo..."
    Expand-Archive -Path $zipPath -DestinationPath $pgDir -Force
    Remove-Item $zipPath -Force
}

if (-not (Test-Path (Join-Path $dataDir "PG_VERSION"))) {
    Write-Host "[3/4] initdb (locale=C, encoding=UTF8, superuser=$superUser)..."
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    & $initdb -D $dataDir -U $superUser --locale=C --encoding=UTF8 -A trust | Out-Null
}

$running = & $pgctl status -D $dataDir 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[4/4] Iniciando PostgreSQL na porta $port (127.0.0.1)..."
    # Inicia via WMI para desanexar do job object do shell (evita 0xC0000142)
    $cmdLine = "`"$pgctl`" start -D `"$dataDir`" -l `"$logFile`" -o `"-p $port -c listen_addresses=127.0.0.1`""
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmdLine }
    if ($result.ReturnValue -ne 0) { throw "Falha ao iniciar o PostgreSQL. Ver $logFile" }
} else {
    Write-Host "PostgreSQL já está rodando."
}

# Espera o servidor aceitar conexões. O start via WMI não suporta `-w`, e um
# sleep fixo é frágil: o psql logo abaixo falha com "the database system is
# starting up" (o consulta do banco volta nula e quebra o `.Trim()`).
$pgIsReady = Join-Path $binDir "pg_isready.exe"
$pronto = $false
for ($i = 0; $i -lt 60; $i++) {
    & $pgIsReady -h 127.0.0.1 -p $port -U $superUser -q 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $pronto = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $pronto) { throw "PostgreSQL não respondeu em 127.0.0.1:$port (ver $logFile)" }

$psql = Join-Path $binDir "psql.exe"
$db   = $(& $psql -h 127.0.0.1 -p $port -d postgres -U $superUser -tAc "SELECT 1 FROM pg_database WHERE datname='printgest'")
if ("$db".Trim() -ne "1") {
    Write-Host "Criando banco 'printgest'..."
    & $psql -h 127.0.0.1 -p $port -d postgres -U $superUser -c "CREATE DATABASE printgest OWNER $superUser" | Out-Null
}

Write-Host "OK. PostgreSQL $version pronto em 127.0.0.1:$port (user=$superUser, db=printgest)"
Write-Host "Binários: $binDir"