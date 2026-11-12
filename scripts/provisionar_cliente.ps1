# Provisiona uma grafica no banco compartilhado do PrintGest (multi-tenant).
#
# Cada grafica recebe um env PROPRIO (com o CNPJ dela) e, opcionalmente, um
# instalador gerado a partir dele. NUNCA reutilizar o mesmo env/instalador
# entre graficas — e exatamente isso que evita o vazamento documentado em
# .lgpd/incidents/.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\provisionar_cliente.ps1 `
#       -Cnpj 32667694000101 -RazaoSocial "Grafica Exemplo Ltda" -Empacotar
#
# Etapas:
#   1. grava installer\env.instalacao (fora do git) a partir do .example,
#      com o CNPJ/razao da grafica e a credencial COMPARTILHADA do banco
#      (lida do backend\.env) e do RedGest;
#   2. valida com scripts\configurar_auth_neon.py --env-file installer\env.instalacao
#      (conexao, migrations, bootstrap do inquilino e estado do admin);
#   3. com -Empacotar, gera o instalador e copia para
#      dist_installer\PrintGest-Setup-<versao>-<cnpj8>.exe (por grafica).

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{14}$')]
    [string]$Cnpj,

    [string]$RazaoSocial = "",
    [string]$FilialNome = "Matriz",
    [switch]$Empacotar,
    [string]$Saida = ""
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

# --- 2) monta o env da instalacao a partir do exemplo, aplicando o inquilino
$linhas = Get-Content $envBase
$definicoes = @{
    'PRINTGEST_DATABASE_URL'        = $fonte['PRINTGEST_DATABASE_URL']
    'PRINTGEST_REDGEST_URL'         = $fonte['PRINTGEST_REDGEST_URL']
    'PRINTGEST_REDGEST_SISTEMA'     = $fonte['PRINTGEST_REDGEST_SISTEMA']
    'PRINTGEST_REDGEST_CONTRATO'    = $fonte['PRINTGEST_REDGEST_CONTRATO']
    'PRINTGEST_REDGEST_API_KEY'     = $fonte['PRINTGEST_REDGEST_API_KEY']
    'PRINTGEST_EMPRESA_CNPJ'        = $Cnpj
    'PRINTGEST_EMPRESA_RAZAO_SOCIAL' = $RazaoSocial
    'PRINTGEST_EMPRESA_FILIAL_NOME' = $FilialNome
}
$saidaEnv = New-Object System.Collections.Generic.List[string]
$usadas = @{}
foreach ($linha in $linhas) {
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

Write-Host "env da instalacao gravado: installer\env.instalacao (CNPJ $Cnpj)"

# --- 3) valida contra o banco compartilhado (migrations + bootstrap do inquilino)
& $python $validador --env-file $envDest
if ($LASTEXITCODE -ne 0) { throw "Validacao falhou para o CNPJ $Cnpj." }

# --- 4) empacota (opcional) e copia o exe com nome por grafica
if ($Empacotar) {
    $empacotar = Join-Path $raiz "scripts\empacotar.ps1"
    if (-not (Test-Path $empacotar)) { throw "Empacotador nao encontrado: $empacotar" }
    & powershell -ExecutionPolicy Bypass -File $empacotar
    if ($LASTEXITCODE -ne 0) { throw "Empacotamento falhou para o CNPJ $Cnpj." }
    $versao = (Select-String -Path (Join-Path $raiz "desktop\printgest\__init__.py") -Pattern '__version__ = "([^"]+)"').Matches.Groups[1].Value
    $cnpj8 = $Cnpj.Substring(0, 8)
    $nome = if ($Saida) { $Saida } else { "PrintGest-Setup-$versao-$cnpj8.exe" }
    $origem = Join-Path $raiz "dist_installer\PrintGest-Setup-$versao.exe"
    $destino = Join-Path $raiz "dist_installer\$nome"
    Copy-Item $origem $destino -Force
    Write-Host "Instalador da grafica: dist_installer\$nome"
}

Write-Host "Pronto. Entregue SOMENTE para a grafica de CNPJ $Cnpj."
