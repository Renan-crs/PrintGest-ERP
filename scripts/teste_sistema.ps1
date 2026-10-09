<#
.SYNOPSIS
  Teste de sistema — sobe o stack completo SIMULANDO o sistema JÁ LICENCIADO.

  Orquestra, de forma idempotente:
    [1/4] PostgreSQL portable (scripts/setup_postgres.ps1)
    [2/4] Licenca ativa semeada (scripts/semear_licenca_ativa.py)
    [3/4] Local API Service no ar SEM PRINTGEST_LICENCA_DESABILITADA
    [4/4] Desktop aberto SEM PRINTGEST_LICENCA_DESABILITADA

  Com a licenca ativa o /v1/licenca retorna status=ativa (modo_leitura=false),
  o middleware libera escritas e o desktop entra direto no dashboard apos o
  login (admin/admin123), sem tela de ativacao.

  Obs.: se quiser manter o modo dev antigo (licenca desabilitada), rode o
  desktop com $env:PRINTGEST_LICENCA_DESABILITADA="true".

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/teste_sistema.ps1
#>

$ErrorActionPreference = "Stop"

$root      = Split-Path -Parent $PSScriptRoot
$backend   = Join-Path $root "backend"
$desktop   = Join-Path $root "desktop"
$pyBack    = Join-Path $backend ".venv\Scripts\python.exe"
$pyDesktop = Join-Path $desktop ".venv\Scripts\python.exe"
$apiUrl    = "http://127.0.0.1:8000/health"

# Garante que a env de dev NAO desabilite a licenca (fluxo real).
Remove-Item Env:PRINTGEST_LICENCA_DESABILITADA -ErrorAction SilentlyContinue

Write-Host "[1/4] Postgres portable..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\setup_postgres.ps1")
if ($LASTEXITCODE -ne 0) { throw "Falha ao subir o Postgres." }

Write-Host "[2/4] Semeando licenca ATIVA..."
$seed = & $pyBack (Join-Path $root "scripts\semear_licenca_ativa.py")
if ($LASTEXITCODE -ne 0) { throw "Falha ao semear a licenca." }
$seed | ForEach-Object { Write-Host "    $_" }

Write-Host "[3/4] Local API Service (licenca real)..."
$noAr = $false
try { Invoke-WebRequest -UseBasicParsing $apiUrl -TimeoutSec 2 | Out-Null; $noAr = $true } catch { $noAr = $false }
if (-not $noAr) {
    Start-Process -FilePath $pyBack -ArgumentList "run_dev.py" -WorkingDirectory $backend -WindowStyle Hidden
    $tentativas = 0
    while ($tentativas -lt 15) {
        Start-Sleep -Seconds 2
        try { Invoke-WebRequest -UseBasicParsing $apiUrl -TimeoutSec 2 | Out-Null; break } catch { }
        $tentativas++
    }
    if ($tentativas -ge 15) { throw "Local API Service nao respondeu em $($tentativas * 2)s." }
    Write-Host "    OK: $apiUrl"
} else {
    Write-Host "    Ja estava no ar: $apiUrl"
}

Write-Host "[4/4] Abrindo o desktop (sem licenca desabilitada)..."
Start-Process -FilePath $pyDesktop -ArgumentList "-m", "printgest.main" -WorkingDirectory $desktop

Write-Host ""
Write-Host "Teste de sistema pronto. Login: admin / admin123"
Write-Host "Estado da licenca:"
try {
    (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/v1/licenca" -TimeoutSec 5).Content
} catch {
    Write-Host "  (nao foi possivel consultar /v1/licenca)"
}