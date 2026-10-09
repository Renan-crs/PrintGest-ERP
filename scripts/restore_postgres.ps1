<#
.SYNOPSIS
  Restaura um backup (.dump) do banco PrintGest.

.DESCRIPTION
  Protocolo 19 (Resiliência de Dados e Backup/DR): restaura um dump criado por
  scripts/backup_postgres.ps1. Use -Recriar para dropar e recriar o banco antes
  (necessário quando o destino já tem objetos). Requer o PostgreSQL portable.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/restore_postgres.ps1 -Arquivo .dev\backups\printgest_20260101_120000.dump -Recriar
#>
param(
    [Parameter(Mandatory = $true)][string]$Arquivo,
    [string]$Banco = "printgest",
    [string]$Usuario = "printgest",
    [string]$Senha = "printgest",
    [string]$Servidor = "127.0.0.1",
    [int]$Porta = 5432,
    [switch]$Recriar
)

$ErrorActionPreference = "Stop"

$root      = Split-Path -Parent $PSScriptRoot
$binDir    = Join-Path $root ".dev\postgres\pgsql\bin"
$pgRestore = Join-Path $binDir "pg_restore.exe"
$psql      = Join-Path $binDir "psql.exe"

foreach ($bin in @($pgRestore, $psql)) {
    if (-not (Test-Path $bin)) {
        throw "Binário não encontrado: $bin. Rode scripts/setup_postgres.ps1."
    }
}
if (-not (Test-Path $Arquivo)) {
    throw "Arquivo de backup não encontrado: $Arquivo"
}

$env:PGPASSWORD = $Senha
try {
    if ($Recriar) {
        Write-Host "Recriando banco '$Banco'..."
        & $psql -h $Servidor -p $Porta -U $Usuario -d postgres -c "DROP DATABASE IF EXISTS $Banco" | Out-Null
        & $psql -h $Servidor -p $Porta -U $Usuario -d postgres -c "CREATE DATABASE $Banco OWNER $Usuario" | Out-Null
    }
    & $pgRestore -h $Servidor -p $Porta -U $Usuario -d $Banco --clean --if-exists $Arquivo
    if ($LASTEXITCODE -ne 0) { throw "pg_restore falhou (exit $LASTEXITCODE)." }
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host "Backup restaurado em '$Banco'."
