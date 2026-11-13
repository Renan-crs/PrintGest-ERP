# Valida (pre-voo) uma grafica no banco compartilhado do PrintGest (multi-tenant)
# e, opcionalmente, gera o instalador UNIVERSAL.
#
# MODELO: um unico instalador para todas as graficas (como Office/Corel) — o
# assistente de instalacao pergunta o CNPJ da grafica e grava no .env da
# instalacao. Nao existe instalador exclusivo por cliente e o .env embutido no
# pacote NAO tem CNPJ. A funcao deste script e garantir que a grafica esta
# pronta (empresa/filial/admin validos) antes de voce distribuir o instalador
# e entregar o CNPJ a ela.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\provisionar_cliente.ps1 `
#       -Cnpj 32667694000101
#   powershell -ExecutionPolicy Bypass -File scripts\provisionar_cliente.ps1 `
#       -Cnpj 01941569000114 -RazaoSocial "Grafica Kurosaki" -Empacotar
#
# Etapas:
#   1. aponta o env de build (installer\env.instalacao) para o CNPJ informado
#      (ambiente compartilhado + credenciais do banco/RedGest);
#   2. valida com scripts\configurar_auth_neon.py --env-file installer\env.instalacao
#      (conexao, migrations, bootstrap do inquilino e estado do admin);
#   3. devolve o env de build ao estado UNIVERSAL (sem CNPJ);
#   4. com -Empacotar, gera o instalador universal (PrintGest-Setup-<versao>.exe).

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{14}$')]
    [string]$Cnpj,

    [string]$RazaoSocial = "",
    [switch]$Empacotar
)

$ErrorActionPreference = "Stop"

$raiz      = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $raiz "installer"
$envBase   = Join-Path $installer "env.instalacao.example"
$envDest   = Join-Path $installer "env.instalacao"
$envDev    = Join-Path $raiz "backend\.env"
$python    = Join-Path $raiz "backend\.venv\Scripts\python.exe"
$validador = Join-Path $raiz "scripts\configurar_auth_neon.py"

foreach ($ferramenta in @($envBase, $envDev, $python, $validador)) {
    if (-not (Test-Path $ferramenta)) { throw "Arquivo nao encontrado: $ferramenta" }
}

# --- 1) credenciais compartilhadas (banco + RedGest) do ambiente de desenvolvimento
$fonte = @{}
Get-Content $envDev | Where-Object { $_ -match '^([A-Z_]+)=(.*)$' } | ForEach-Object {
    $fonte[$Matches[1]] = $Matches[2].Trim()
}
foreach ($chave in @('PRINTGEST_DATABASE_URL', 'PRINTGEST_REDGEST_URL', 'PRINTGEST_REDGEST_SISTEMA', 'PRINTGEST_REDGEST_CONTRATO')) {
    if (-not $fonte.ContainsKey($chave) -or -not $fonte[$chave]) {
        throw "Falta $chave no $envDev (fonte das credenciais compartilhadas)."
    }
}

# --- 2) monta o env de build a partir do exemplo, aplicando o inquilino da vez
$definicoes = @{
    'PRINTGEST_DATABASE_URL'         = $fonte['PRINTGEST_DATABASE_URL']
    'PRINTGEST_REDGEST_URL'          = $fonte['PRINTGEST_REDGEST_URL']
    'PRINTGEST_REDGEST_SISTEMA'      = $fonte['PRINTGEST_REDGEST_SISTEMA']
    'PRINTGEST_REDGEST_CONTRATO'     = $fonte['PRINTGEST_REDGEST_CONTRATO']
    'PRINTGEST_REDGEST_API_KEY'      = $fonte['PRINTGEST_REDGEST_API_KEY']
    'PRINTGEST_EMPRESA_CNPJ'         = $Cnpj
    'PRINTGEST_EMPRESA_RAZAO_SOCIAL' = $RazaoSocial
}
$saidaEnv = New-Object System.Collections.Generic.List[string]
$usadas = @{}
foreach ($linha in (Get-Content $envBase)) {
    if ($linha -match '^([A-Z_]+)=(.*)$') {
        $chave = $Matches[1]
        if ($definicoes.ContainsKey($chave)) {
            $saidaEnv.Add("$chave=$($definicoes[$chave])")
            $usadas[$chave] = $true
            continue
        }
    }
    $saidaEnv.Add($linha)
}
foreach ($chave in $definicoes.Keys) {
    if (-not $usadas.ContainsKey($chave)) { $saidaEnv.Add("$chave=$($definicoes[$chave])") }
}
[System.IO.File]::WriteAllLines($envDest, $saidaEnv, (New-Object System.Text.UTF8Encoding($false)))

# --- 3) valida contra o banco compartilhado (migrations + bootstrap do inquilino)
& $python $validador --env-file $envDest
if ($LASTEXITCODE -ne 0) { throw "Validacao falhou para o CNPJ $Cnpj." }

# --- 4) devolve o env de build ao estado UNIVERSAL (sem CNPJ no pacote)
$saidaEnv = New-Object System.Collections.Generic.List[string]
foreach ($linha in (Get-Content $envDest)) {
    if ($linha -match '^PRINTGEST_EMPRESA_(CNPJ|RAZAO_SOCIAL|FILIAL_NOME)\s*=') { continue }
    $saidaEnv.Add($linha)
}
[System.IO.File]::WriteAllLines($envDest, $saidaEnv, (New-Object System.Text.UTF8Encoding($false)))

# --- 5) empacota o instalador universal (opcional)
if ($Empacotar) {
    $empacotar = Join-Path $raiz "scripts\empacotar.ps1"
    if (-not (Test-Path $empacotar)) { throw "Empacotador nao encontrado: $empacotar" }
    & powershell -ExecutionPolicy Bypass -File $empacotar
    if ($LASTEXITCODE -ne 0) { throw "Empacotamento falhou." }
    Write-Host "Instalador universal gerado em dist_installer\ (PrintGest-Setup-<versao>.exe)"
}

Write-Host "Gráfica $Cnpj validada. O instalador e universal: na instalação, informe o CNPJ."
