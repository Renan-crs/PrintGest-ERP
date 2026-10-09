<#
.SYNOPSIS
  Gera um backup lógico (pg_dump -Fc) do banco PrintGest.

.DESCRIPTION
  Protocolo 19 (Resiliência de Dados e Backup/DR): produz um dump restaurável
  (custom format) em .dev/backups com carimbo de data/hora. Requer o PostgreSQL
  portable iniciado (scripts/setup_postgres.ps1).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/backup_postgres.ps1 -Saida D:\backups\printgest.dump
#>
param(
    [string]$Banco = "printgest",
    [string]$Usuario = "printgest",
    [string]$Senha = "printgest",
    [string]$Servidor = "127.0.0.1",
    [int]$Porta = 5432,
    [string]$Saida
)

$ErrorActionPreference = "Stop"

$root      = Split-Path -Parent $PSScriptRoot
$binDir    = Join-Path $root ".dev\postgres\pgsql\bin"
$pgDump    = Join-Path $binDir "pg_dump.exe"
$backupDir = Join-Path $root ".dev\backups"

if (-not (Test-Path $pgDump)) {
    throw "pg_dump não encontrado em $pgDump. Rode scripts/setup_postgres.ps1."
}
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (-not $Saida) {
    $carimbo = Get-Date -Format "yyyyMMdd_HHmmss"
    $Saida = Join-Path $backupDir "printgest_$carimbo.dump"
}

$env:PGPASSWORD = $Senha
try {
    & $pgDump -h $Servidor -p $Porta -U $Usuario -d $Banco -Fc -f $Saida
    if ($LASTEXITCODE -ne 0) { throw "pg_dump falhou (exit $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Backup criado: $Saida"
