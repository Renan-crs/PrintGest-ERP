# Empacota o PrintGest ERP em UM instalador Inno Setup (com desinstalador).
#
# O wizard da instalacao pergunta se a maquina e SERVIDOR ou ESTACAO:
#   - Servidor: grava o .env do Neon (credenciais) e atende as estacoes;
#   - Estacao:  grava apenas PRINTGEST_API_URL / PRINTGEST_MODO_ESTACAO.
# Ambos os binarios viajam no Setup; nenhuma credencial e gravada na estacao.
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
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
    # Mantido por compatibilidade com scripts antigos: o valor NAO altera o
    # pacote — sempre e gerado o instalador unico.
    [ValidateSet("unico", "servidor", "estacao")]
    [string]$Modo = "unico"
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

$sufixo = ""  # instalador unico: sem sufixo de modo

foreach ($ferramenta in @($pyDesktop, $pyApi, $iscc)) { if (-not (Test-Path $ferramenta)) { throw "Ferramenta nao encontrada: $ferramenta" } }

# Versao do pacote sai do proprio desktop (fonte unica da verdade).
$versao = (Select-String -Path (Join-Path $raiz "desktop\printgest\__init__.py") `
    -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if ($Modo -ne "unico") {
    Write-Host "[i] -Modo $Modo ignorado: este script gera sempre o instalador unico."
}
Write-Host "== PrintGest ERP $versao (instalador unico) =="

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
$contrato = ""
$apiChave = ""
# Configuracao do servidor sempre e lida: o instalador unico a embute e so
# grava no disco quando o wizard escolher Servidor.
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
    
    # Ler as chaves antes de filtrar
    $contrato = Ler-Chave (Get-Content $envBase) "PRINTGEST_REDGEST_CONTRATO"
    $apiChave = Ler-Chave (Get-Content $envBase) "PRINTGEST_REDGEST_API_KEY"
    
    # Instalador UNIVERSAL: o CNPJ/razao da gráfica NÃO vai no .env embutido —
    # o assistente de instalação pergunta e grava no .env da instalação.
    $linhas = @(Get-Content $envBase | Where-Object {
        $_ -notmatch '^\s*PRINTGEST_(PG_EMBARCADO|API_HOST|ENV|DATABASE_URL|EMPRESA_CNPJ|EMPRESA_RAZAO_SOCIAL|EMPRESA_FILIAL_NOME)\s*='
    })
    
    # Extrair DATABASE_URL se existir (apenas o valor, sem o nome da variável)
    if (Test-Path $envBase) {
        $lines = Get-Content $envBase
        foreach ($line in $lines) {
            if ($line -match '^PRINTGEST_DATABASE_URL\s*=\s*(.+)$') {
                $databaseUrl = $Matches[1].Trim()
                break
            }
        }
    }
    
    if ($contrato -eq "c" -and -not $apiChave) {
        throw @"
Contrato C exige PRINTGEST_REDGEST_API_KEY, e ela esta vazia.
Preencha em installer\env.instalacao (copie do .example; esse nome e ignorado
pelo git) - a validacao da chave de produto e assinada com essa credencial.
Contrato B (CNPJ + codigo) NAO usa api_key e pode seguir sem ela.
"@
    }
    if ($apiChave) {
        Write-Host ("  ATENCAO: o pacote carrega a api_key do RedGest ({0}...{1})." -f $apiChave.Substring(0,5), $apiChave.Substring($apiChave.Length-3))
    } else {
        Write-Host "  api_key: AUSENTE do pacote (Contrato B nao precisa)."
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

# ------------------------------------- 3) backend (presente no instalador unico)
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
# DATABASE_URL deve vir antes das outras variaveis - valor já limpo
$dbUrlVar = if ($databaseUrl) {
    "PRINTGEST_DATABASE_URL=$databaseUrl"
} else {
    ""
}
$conteudo = @($dbUrlVar) + $linhas + @(
    "",
    "# Instalacao empacotada (gerado por scripts/empacotar.ps1)",
    "# Inquilino (PRINTGEST_EMPRESA_CNPJ) e gravado pelo assistente de",
    "# instalacao no .env desta pasta - instalador universal para todas",
    "# as graficas."
) + @($forcadas.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" })

# Copia de desenvolvimento (fora do Setup: Excludes *.env) e TEMPLATE que o
# wizard so transforma em .env quando o operador escolher SERVIDOR.
$conteudo | Set-Content -Path (Join-Path $dist "PrintGestAPI\.env") -Encoding utf8
$conteudo | Set-Content -Path (Join-Path $pacote "config-servidor.txt") -Encoding utf8
Write-Host "[i] Template de credenciais: build\pacote\config-servidor.txt (gravado so no modo Servidor)."

# ------------------------------------------------------------- 4) LEIA-ME
$leiaMe = @"
PrintGest ERP $versao — instalador unico

O wizard pergunta se este computador e SERVIDOR ou ESTACAO.

SERVIDOR (uma maquina por CNPJ/licenca)
  1. Abra o PrintGest ERP. O sistema se conecta ao Neon Database (pode levar
     alguns segundos na primeira execucao).
  2. A tela de ativacao pede a licenca emitida pelo RedGest (CNPJ + codigo).
  3. Login do administrador: usuario "admin", senha de fabrica "admin123".
     Troque a senha no primeiro login.
  4. Para atender as estacoes na rede, ajuste PRINTGEST_API_HOST no .env de
     PrintGestAPI para o IP do servidor e libere a porta 8000/TCP.
  5. Cadastre a equipe em Cadastro de Funcionarios; cada usuario define a
     propria senha no primeiro acesso.

ESTACAO (demais maquinas)
  1. Escolha "Estacao" e informe o endereco do servidor, por exemplo
     192.168.0.10:8000 (pode ser trocado na tela Conectar ao Servidor).
  2. Faca login com um usuario criado no servidor. Nao ha ativacao local,
     nao ha daemon e nenhuma credencial do Neon e gravada nesta maquina.

ONDE FICAM AS COISAS
  - Programa:        {localappdata}\Programs\PrintGest
  - Log do servico:  ...\PrintGest\PrintGestAPI\logs\printgest-api.log
  - Modo escolhido:  ...\PrintGest\modo.txt (usado nas atualizacoes silenciosas)

DESINSTALACAO
  Use "Desinstalar PrintGest ERP" no menu Iniciar ou Aplicativos do Windows.
  A desinstalacao encerra os processos e remove o programa. Os dados do
  cliente ficam no Neon e NAO sao apagados.

Suporte: veja docs/empacotamento.md e docs/topologia_homologacao.md.
"@
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
    $alvos = @(
        (Join-Path $dist "PrintGest\PrintGest.exe"),
        (Join-Path $dist "PrintGestAPI\PrintGestAPI.exe")
    )
    foreach ($exe in $alvos) { Assinar-Exe $exe $signtool $Assinar }
} else {
    Write-Host "[i] Sem assinatura digital (-Assinar <thumbprint-ou-.pfx> para assinar)."
    Write-Host "    O Windows pode avisar sobre o SmartScreen na primeira execucao do Setup."
}

# --------------------------------------------------- 6) instalador Inno Setup
Write-Host "[4/4] Compilando o instalador Inno Setup (unico)..."
$saidaAbs = Join-Path $raiz $Saida
if (-not (Test-Path $saidaAbs)) { New-Item -ItemType Directory -Force -Path $saidaAbs | Out-Null }
$defines = @("/O$saidaAbs", "/DVersaoApp=$versao")
& $iscc $defines (Join-Path $installer "PrintGest.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$setup = Join-Path $saidaAbs "PrintGest-Setup-$versao$sufixo.exe"
if (-not (Test-Path $setup)) { throw "Setup nao encontrado em $setup (verifique OutputBaseFilename do .iss)." }

# O proprio Setup tambem e assinado (e o que dispara/dispensa o SmartScreen).
if ($Assinar -ne "") {
    Assinar-Exe $setup $signtool $Assinar
}

# Manifesto `latest.json` — publicado como asset da release para o aviso de
# nova versao no desktop (Fase 1: apenas notifica, nunca instala sozinho).
$hashSetup = (Get-FileHash -Algorithm SHA256 -LiteralPath $setup).Hash.ToLowerInvariant()
$manifesto = [ordered]@{
    versao = $versao
    arquivo = "PrintGest-Setup-$versao.exe"
    sha256 = $hashSetup
    data = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
    url = "https://github.com/Renan-crs/PrintGest-ERP/releases/tag/v$versao"
    notas = @("Instalador unico (Servidor ou Estacao escolhidos no wizard) - sem UAC, dados do cliente preservados.")
}
$jsonManifesto = $manifesto | ConvertTo-Json -Depth 4
$destinoManifesto = Join-Path $saidaAbs "latest.json"
[System.IO.File]::WriteAllText(
    $destinoManifesto, $jsonManifesto, (New-Object System.Text.UTF8Encoding($false))
)
Write-Host "[i] Manifesto de atualizacao: $destinoManifesto"

$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "OK: $setup ($mb MB)"
Write-Host "No wizard escolha SERVIDOR (uma maquina por CNPJ/licenca) ou ESTACAO (informe o endereco do servidor)."