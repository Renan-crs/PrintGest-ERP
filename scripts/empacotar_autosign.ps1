# Empacota o PrintGest ERP com assinatura auto-assinada
# Util para testes internos e ambientes sem certificado pago.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar_autosign.ps1

param(
    [string]$Saida = "dist_installer",
    [ValidateSet("servidor", "estacao")]
    [string]$Modo = "servidor"
)

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot

# ---------------------------------- 1) Criar certificado auto-assinado
Write-Host "[1/4] Gerando certificado de auto-assinatura..."
$certificado = New-SelfSignedCertificate `
    -Type CodeSigning `
    -Subject "CN=PrintGest ERP - Auto-assinado" `
    -KeyUsage DigitalSignature `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -FriendlyName "PrintGest Code Signing (Auto)" `
    -NotAfter (Get-Date).AddYears(1)

$thumbprint = $certificado.Thumbprint
Write-Host "    Certificado criado: $thumbprint"

# ---------------------------------- 2) Assinar e empacotar
Write-Host "[2/4] Empacotando com assinatura..."
try {
    & "$raiz/scripts/empacotar.ps1" -Saida $Saida -Modo $Modo -Assinar $thumbprint
    Write-Host ""
    Write-Host "OK: Instalador criado com assinatura auto-assinada!"
    Write-Host ""
    Write-Host "NOTA: O Windows SmartScreen ainda pode mostrar aviso na primeira execucao."
    Write-Host "Isso e normal para certificados auto-assinados."
    Write-Host ""
    Write-Host "Para evitar avisos no futuro, adquira um certificado de codigo real."
    Write-Host ""
} catch {
    Write-Host "ERRO durante o empacotamento: $_" -ForegroundColor Red
    exit 1
}