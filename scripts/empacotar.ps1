# Empacota o PrintGest ERP em um instalador unico (Inno Setup) com desinstalador.
#
# Etapas:
#   1. PrintGestAPI.exe  - backend FastAPI/uvicorn (PyInstaller onedir)
#   2. PrintGest.exe     - desktop PySide6 (PyInstaller onedir)
#   3. PostgreSQL 16     - binarios podados (sem pgAdmin/doc/include)
#   4. .env da instalacao - gerado de installer/env.instalacao(.example),
#                          SEM ler o backend/.env de dev (nao vaza segredos)
#   5. PrintGest-Setup-<versao>.exe - instalador Inno Setup (unins000.exe incluso)
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
#
# Assinatura digital (opcional - exige certificado de code signing):
#   powershell ... -File scripts\empacotar.ps1 -Assinar <thumbprint-ou-arquivo.pfx>
#   Senha do .pfx: variavel de ambiente PRINTGEST_SIGN_SENHA.
#
# Requisitos: venvs de backend/desktop com PyInstaller, PostgreSQL de dev em
# .dev\postgres\pgsql (scripts\setup_postgres.ps1) e Inno Setup 6.

param(
    [string]$Saida = "dist_installer",
    # Thumbprint do certificado em Cert:\CurrentUser\My OU caminho de um .pfx.
    # Vazio = nao assina (o Windows pode mostrar SmartScreen no Setup).
    [string]$Assinar = ""
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

foreach ($ferramenta in @($pyApi, $pyDesktop, $iscc)) {
    if (-not (Test-Path $ferramenta)) {
        throw "Ferramenta nao encontrada: $ferramenta"
    }
}

# Versao do pacote sai do proprio desktop (fonte unica da verdade).
$versao = (Select-String -Path (Join-Path $raiz "desktop\printgest\__init__.py") `
    -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "== PrintGest ERP $versao =="

# ------------------------------------------- 0) .env da instalacao (validado
# ANTES de qualquer build: um contrato c sem api_key nao pode gastar 4 min de
# PyInstaller para descobrir que o pacote nao pode ser gerado.
function Ler-Chave([string[]]$conteudo, [string]$chave) {
    foreach ($linha in $conteudo) {
        if ($linha -match ("^\s*" + $chave + "\s*=\s*(.*)\s*$")) { return $Matches[1] }
    }
    return ""
}

# Fonte: installer/env.instalacao quando existir (credenciais por cliente, fora
# do git); senao o template versionado. NUNCA o backend/.env de dev.
$envLocal = Join-Path $installer "env.instalacao"
$envExemplo = Join-Path $installer "env.instalacao.example"
$envBase = if (Test-Path $envLocal) { $envLocal } else { $envExemplo }
if ($envBase -eq $envLocal) {
    Write-Host "  base do .env: env.instalacao (credenciais locais, fora do git)"
} else {
    Write-Host "  base do .env: env.instalacao.example (template publico)"
}
$linhas = @(Get-Content $envBase | Where-Object {
    $_ -notmatch '^\s*PRINTGEST_(PG_EMBARCADO|API_HOST|ENV)\s*='
})

$contrato = Ler-Chave $linhas "PRINTGEST_REDGEST_CONTRATO"
$apiChave = Ler-Chave $linhas "PRINTGEST_REDGEST_API_KEY"
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
    throw "PostgreSQL de dev nao encontrado em $pgOrigem (rode scripts\setup_postgres.ps1)."
}
# pgAdmin 4 (~673 MB), doc, include e StackBuilder nao sao usados em runtime;
# wx*.dll/ecpg pertencem a ferramentas fora do fluxo servidor.
robocopy $pgOrigem $pgDestino /E /NFL /NDL /NJH /NJS /NP `
    /XD "pgAdmin 4" "doc" "include" "StackBuilder" "symbols" `
    /XF "wx*.dll" "ecpg.exe" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy do PostgreSQL falhou (codigo $LASTEXITCODE)." }
$LASTEXITCODE = 0

# ------------------------------------------------------ 5) .env da instalacao
Write-Host "[4/5] Gerando o .env da instalacao..."

# Chaves fixas da instalacao empacotada (as demais vem do template carregado):
#   PG_EMBARCADO  -> o daemon prepara o cluster na primeira execucao
#   API_HOST      -> 127.0.0.1: sem prompt de firewall, sem expor a API
#   ENV           -> "local" passa na checagem anti-defaults de producao
$forcadas = @{
    "PRINTGEST_PG_EMBARCADO" = "true"
    "PRINTGEST_API_HOST"     = "127.0.0.1"
    "PRINTGEST_ENV"          = "local"
}
$conteudo = @($linhas) + @(
    "",
    "# Instalacao empacotada (gerado por scripts/empacotar.ps1)"
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

# ------------------------------------------- 8) assinatura digital (opcional)
function Resolve-Signtool {
    $candidatos = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" `
        -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "\\x64\\" } |
        Sort-Object FullName -Descending
    if ($candidatos) { return $candidatos[0].FullName }
    throw "signtool.exe nao encontrado - instale o Windows SDK."
}

function Assinar-Exe([string]$exe, [string]$signtool, [string]$modo) {
    # $modo: thumbprint (store) ou caminho .pfx
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
    foreach ($exe in @(
        (Join-Path $dist "PrintGest\PrintGest.exe"),
        (Join-Path $dist "PrintGestAPI\PrintGestAPI.exe")
    )) {
        Assinar-Exe $exe $signtool $Assinar
    }
} else {
    Write-Host "[i] Sem assinatura digital (-Assinar <thumbprint-ou-.pfx> para assinar)."
    Write-Host "    O Windows pode avisar sobre o SmartScreen na primeira execucao do Setup."
}

# --------------------------------------------------- 7) instalador Inno Setup
Write-Host "[5/5] Compilando o instalador Inno Setup..."
$saidaAbs = Join-Path $raiz $Saida
if (-not (Test-Path $saidaAbs)) { New-Item -ItemType Directory -Force -Path $saidaAbs | Out-Null }
& $iscc "/O$saidaAbs" "/DVersaoApp=$versao" (Join-Path $installer "PrintGest.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$setup = Join-Path $saidaAbs "PrintGest-Setup-$versao.exe"

# O proprio Setup tambem e assinado (e o que dispara/dispensa o SmartScreen).
if ($Assinar -ne "") {
    Assinar-Exe $setup $signtool $Assinar
}

$mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "OK: $setup ($mb MB)"
Write-Host "Instale em outra maquina: execucao dupla, sem UAC (instalacao por usuario)."
