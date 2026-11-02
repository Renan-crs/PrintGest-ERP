# Empacota o PrintGest ERP em instaladores Inno Setup (com desinstalador).
#
# Modo SERVIDOR (padrao) - desktop + Local API Service + Neon Database.
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
#
# Modo ESTACAO - apenas o desktop; o assistente pergunta o endereco do
# servidor (PRINTGEST_API_URL gravado em .env ao lado do exe):
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1 -Modo estacao
#
# Assinatura digital (opcional - exige certificado de code signing):
#   ... -Assinar <thumbprint-ou-arquivo.pfx>  (senha em PRINTGEST_SIGN_SENHA)
#
# Requisitos: venvs de backend/desktop com PyInstaller e Inno Setup 6.

param(
    [string]$Saida = "dist_installer",
    # Thumbprint do certificado em Cert:\CurrentUser\My OU caminho de um .pfx.
    # Vazio = nao assina (o Windows pode mostrar SmartScreen no Setup).
    [string]$Assinar = "",
    [ValidateSet("servidor", "estacao")]
    [string]$Modo = "servidor"
)

$ErrorActionPreference = "Stop"

$raiz      = Split-Path -Parent $PSScriptRoot
$build     = Join-Path $raiz "build"
$dist      = Join-Path $build "dist"
$pacote    = Join-Path $build "pacote"
$installer = Join-Path $raiz "installer"
$pyApi     = Join-Path $raiz "backend\.venv\Scripts\pyinstaller.exe"
$pyDesktop = Join-Path $raiz "desktop\.venv\Scripts\pyinstaller.exe"
$iscc      = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

$ehServidor = ($Modo -eq "servidor")
$sufixo = if ($ehServidor) { "" } else { "Estacao" }

foreach ($ferramenta in @($pyDesktop, $iscc)) { if (-not (Test-Path $ferramenta)) { throw "Ferramenta nao encontrada: $ferramenta" } }
if ($ehServidor -and -not (Test-Path $pyApi)) { throw "Ferramenta nao encontrada: $pyApi" }

# Versao do pacote sai do proprio desktop (fonte unica da verdade).
$versao = (Select-String -Path (Join-Path $raiz "desktop\printgest\__init__.py") `
    -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "== PrintGest ERP $versao (modo: $Modo) =="

# ------------------------------------------- 0) .env da instalacao (validado
# ANTES de qualquer build: um contrato c sem api_key nao pode gastar 4 min de
# PyInstaller para descobrir que o pacote nao pode ser gerado.
function Ler-Chave([string[]]$conteudo, [string]$chave) {
    foreach ($linha in $conteudo) {
        if ($linha -match ("^\s*" + $chave + "\s*=\s*(.*)\s*$")) { return $Matches[1] }
    }
    return ""
}

$linhas = $null
$databaseUrl = ""
if ($ehServidor) {
    # Fonte do .env: env.instalacao.neon ou env.instalacao.example
    $envNeon = Join-Path $installer "env.instalacao.neon"
    $envLocal = Join-Path $installer "env.instalacao"
    $envExemplo = Join-Path $installer "env.instalacao.example"
    
    $envBase = $envExemplo
    if (Test-Path $envLocal) {
        $conteudoLocal = Get-Content $envLocal -ErrorAction SilentlyContinue
        if ($conteudoLocal -and ($conteudoLocal -match "PRINTGEST_DATABASE_URL=")) {
            if ($conteudoLocal -notmatch "__NEON") {
                $envBase = $envLocal
            }
        }
    }
    if ($envBase -eq $envExemplo -and (Test-Path $envNeon)) {
        $envBase = $envNeon
    }
    
    if ($envBase -eq $envLocal) {
        Write-Host "  base do .env: env.instalacao (credenciais Neon reais)"
    } elseif ($envBase -eq $envNeon) {
        Write-Host "  base do .env: env.instalacao.neon (template Neon)"
    } else {
        Write-Host "  base do .env: env.instalacao.example (template publico)"
    }
    
    $linhas = @(Get-Content $envBase | Where-Object {
        $_ -notmatch '^\s*PRINTGEST_(PG_EMBARCADO|API_HOST|ENV)\s*='
    })
    
    # Extrair DATABASE_URL se existir (apenas o valor, sem o nome da variável)
    if (Test-Path $envBase) {
        $dbUrlLine = Select-String -Path $envBase -Pattern '^PRINTGEST_DATABASE_URL\s*=' -SimpleMatch -ErrorAction SilentlyContinue
        if ($dbUrlLine) {
            $match = $dbUrlLine.Line -match '^PRINTGEST_DATABASE_URL\s*=\s*(.+)$'
            if ($match) {
                $databaseUrl = $Matches[1]
            } else {
                $databaseUrl = $dbUrlLine.Line.Trim()
            }
        }
    }
    
    if ($apiChave) {
        Write-Host ("  ATENCAO: o pacote carrega a api_key do RedGest ({0}...{1})." -f $apiChave.Substring(0,5), $apiChave.Substring($apiChave.Length-3))
    } else {
        Write-Host "  api_key: AUSENTE do pacote (Contrato B nao precisa)."
    }
}

# ------------------------------------------------------------ 1) limpeza
foreach ($alvo in @((Join-Path $dist "PrintGest"), (Join-Path $dist "PrintGestAPI"))) {
    if (Test-Path $alvo) { Remove-Item -Recurse -Force $alvo }
}

# ---------------------------------------------------- 2) desktop (PrintGest)
Write-Host "[1/4] PyInstaller: PrintGest.exe (desktop)..."
Push-Location $installer
try {
    & $pyDesktop "printgest.spec" --clean --noconfirm --distpath (Join-Path $dist "") --workpath (Join-Path $build "work_desktop")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou no desktop." }
} finally { Pop-Location }

# ------------------------------------- 3) backend (so servidor)
if ($ehServidor) {
    Write-Host "[2/4] PyInstaller: PrintGestAPI.exe (backend)..."
    Push-Location $installer
    try {
        & $pyApi "printgestapi.spec" --clean --noconfirm --distpath (Join-Path $dist "") --workpath (Join-Path $build "work_api")
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou no backend." }
    } finally { Pop-Location }

    # Neon Database: PostgreSQL embarcado REMOVIDO (v0.3.4+)
    # .env da instalacao (chaves fixas impostas pelo build):
    $forcadas = @{
        "PRINTGEST_PG_EMBARCADO" = "false"
        "PRINTGEST_API_HOST"     = "127.0.0.1"
        "PRINTGEST_ENV"          = "local"
    }
    # DATABASE_URL deve vir antes das outras variaveis
    $dbUrlVar = if ($databaseUrl) {
        if ($databaseUrl -match "^[A-Z_]+=.*") { $databaseUrl } else { "PRINTGEST_DATABASE_URL=$databaseUrl" }
    } else {
        ""
    }
    $conteudo = @($dbUrlVar) + $linhas + @(
        "",
        "# Instalacao empacotada (gerado por scripts/empacotar.ps1)"
    ) + @($forcadas.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" })
    $conteudo | Set-Content -Path (Join-Path $dist "PrintGestAPI\.env") -Encoding utf8
} else {
    Write-Host "[2/4] modo estacao: sem backend/PostgreSQL no pacote."
    Write-Host "[3/4] modo estacao: .env com o endereco sera gravado pelo assistente."
}

# ------------------------------------------------------------- 4) LEIA-ME
$leiaMe = if ($ehServidor) { @"
PrintGest ERP $versao (Servidor)

PRIMEIRA EXECUCAO
  1. Abra o PrintGest ERP (atalho da area de trabalho / menu Iniciar).
  2. O sistema se conecta ao Neon Database (nao ha banco local - levou alguns segundos).
  3. A tela de ativacao pede a licenca emitida pelo RedGest - como em
     programas licenciados por serial, ela so e pedida na instalacao.
  4. Faca login com o usuario inicial: admin / admin123 (troque a senha
     no primeiro acesso, em Configuracao > Usuarios e Niveis).

ONDE FICAM AS COISAS
  - Programa:        {localappdata}\Programs\PrintGest
  - Log do servico:  ...\PrintGest\PrintGestAPI\logs\printgest-api.log

DESINSTALACAO
  Use "Desinstalar PrintGest ERP" no menu Iniciar ou Aplicativos do Windows.
  A desinstalacao encerra o servico e remove o programa. Os dados sao mantidos
  no Neon Database em nuvem - exporte antes, se precisar.

Suporte: veja docs/empacotamento.md no repositorio.
"@ } else { @"
PrintGest ERP $versao (Estacao)

ESTA MAQUINA E UMA ESTACAO
  O sistema e o banco de dados ficam no SERVIDOR da grafica. Este pacote
  instala apenas o programa; o endereco do servidor foi pedido na instalacao
  (e pode ser trocado dentro do programa, na tela Conectar ao Servidor).

PRIMEIRA EXECUCAO
  1. Abra o PrintGest ERP (atalho da area de trabalho / menu Iniciar).
  2. Se o endereco ainda nao estiver configurado, a tela Conectar ao
     Servidor pede - use algo como 192.168.0.10:8000.
  3. Faca login com o usuario criado no servidor (a licenca e a senha
     sao gerenciadas la).

DESINSTALACAO
  Use "Desinstalar PrintGest ERP Estacao" no menu Iniciar ou Aplicativos
  do Windows. Nenhum dado e removido - tudo vive no servidor.

Suporte: veja docs/empacotamento.md no repositorio.
"@ }
$leiaMe | Set-Content -Path (Join-Path $pacote "LEIA-ME.txt") -Encoding utf8

# ------------------------------------------- 5) assinatura digital (opcional)
function Resolve-Signtool {
    $candidatos = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" `
        -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\" } |
        Sort-Object FullName -Descending
    if ($candidatos) { return $candidatos[0].FullName }
    throw "signtool.exe nao encontrado - instale o Windows SDK."
}

function Assinar-Exe([string]$exe, [string]$signtool, [string]$modo) {
    $carimbo = "http://timestamp.digicert.com"
    if ($env:PRINTGEST_SIGN_CARIMBO) { $carimbo = $env:PRINTGEST_SIGN_CARIMBO }
    $argumentos = @("sign", "/fd", "SHA256", "/tr", $carimbo, "/td", "SHA256")
    if (Test-Path $modo) {
        $argumentos += @("/f", $modo)
        if ($env:PRINTGEST_SIGN_SENHA) { $argumentos += @("/p", $env:PRINTGEST_SIGN_SENHA) }
    } else {
        $argumentos += @("/sha1", $modo)
    }
    & $signtool sign ($argumentos + @($exe))
    if ($LASTEXITCODE -ne 0) { throw "Falha ao assinar $exe" }
    & $signtool verify /pa $exe
    if ($LASTEXITCODE -ne 0) { throw "Assinatura de $exe nao verificou" }
    Write-Host "    assinado: $exe"
}

# Os exes precisam ser assinados ANTES do ISCC empacota-los no Setup.
if ($Assinar -ne "") {
    Write-Host "[+] Assinando os executaveis (signtool)..."
    $signtool = Resolve-Signtool
    $alvos = @((Join-Path $dist "PrintGest\PrintGest.exe"))
    if ($ehServidor) { $alvos += (Join-Path $dist "PrintGestAPI\PrintGestAPI.exe") }
    foreach ($exe in $alvos) { Assinar-Exe $exe $signtool $Assinar }
} else {
    Write-Host "[i] Sem assinatura digital (-Assinar <thumbprint-ou-.pfx> para assinar)."
    Write-Host "    O Windows pode avisar sobre o SmartScreen na primeira execucao do Setup."
}

# --------------------------------------------------- 6) instalador Inno Setup
Write-Host "[4/4] Compilando o instalador Inno Setup (modo: $Modo)..."
$saidaAbs = Join-Path $raiz $Saida
if (-not (Test-Path $saidaAbs)) { New-Item -ItemType Directory -Force -Path $saidaAbs | Out-Null }
$defines = @("/O$saidaAbs", "/DVersaoApp=$versao")
if (-not $ehServidor) { $defines += "/DModoEstacao" }
& $iscc $defines (Join-Path $installer "PrintGest.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$setup = Join-Path $saidaAbs "PrintGest-Setup-$versao$sufixo.exe"
if (-not (Test-Path $setup)) { throw "Setup nao encontrado em $setup (verifique OutputBaseFilename do .iss)." }

# O proprio Setup tambem e assinado (e o que dispara/dispensa o SmartScreen).
if ($Assinar -ne "") {
    Assinar-Exe $setup $signtool $Assinar
}

$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "OK: $setup ($mb MB)"
if ($ehServidor) {
    Write-Host "Maquina SERVIDORA da grafica: duplo clique, sem UAC (instalacao por usuario)."
} else {
    Write-Host "Maquina de ESTACAO: duplo clique - o assistente pede o endereco do servidor."
}