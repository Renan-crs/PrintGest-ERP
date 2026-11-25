<#
.SYNOPSIS
  Valida a regra crítica do instalador (PRD v3.3): encerrar a API antes de
  atualizar e NUNCA apagar dados do cliente. Roda sem Inno Setup — checa o
  texto-fonte do PrintGest.iss e falha se alguma protegia sumir.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\validar_regra_instalador.ps1
#>

$ErrorActionPreference = 'Stop'
$iss = Join-Path $PSScriptRoot '..\installer\PrintGest.iss'
$conteudo = Get-Content $iss -Raw
$falhas = @()

function Exigir([string]$descricao, [string]$padrao) {
  if ($conteudo -notmatch $padrao) {
    $script:falhas += $descricao
  }
}

# 1) Encerrar API e desktop ANTES de copiar (PrepareToInstall do Inno Setup).
Exigir 'PrepareToInstall ausente (deve encerrar processos na atualizacao)' 'function PrepareToInstall'
Exigir 'PrintGestAPI.nao e encerrado antes da atualizacao' "EncerrarProcesso\('PrintGestAPI\.exe'\)"
Exigir 'PrintGest.nao e encerrado antes da atualizacao' "EncerrarProcesso\('PrintGest\.exe'\)"
Exigir 'taskkill ausente' 'taskkill\.exe'

# 2) Repetir emissao sem apagar dados: excluir dados do pacote.
Exigir 'Excludes nao protege .env/cofres/dumps' 'Excludes:.*\.env'
Exigir 'Excludes nao protege *.dat' '\*\.dat'
Exigir 'Excludes nao protege *.dump' '\*\.dump'

# 3) Desinstalacao/atualizacao nao pode apagar a pasta de dados do servidor.
if ($conteudo -match 'filesandordirs;\s*Name:\s*"\{app\}\\PrintGestAPI"') {
  $falhas += 'UninstallDelete apaga {app}\PrintGestAPI inteiro (perde .env/cofres)'
}

# 4) .env da estacao continua gravado pelo assistente (comportamento existente).
Exigir 'assistente da estacao nao grava .env' 'PRINTGEST_API_URL='

# 5) Atualizacao silenciosa NAO pode sobrescrever o .env da estacao (Fase 2).
Exigir 'atualizacao silenciosa pode apagar o endereco do servidor' 'Endereco = ''''\) and FileExists\(EnvPath\)'
Exigir 'guarda de preservacao do .env sem log' 'preservando \.env da estacao'

if ($falhas.Count -gt 0) {
  Write-Host 'FALHA na regra do instalador:' -ForegroundColor Red
  $falhas | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
  exit 1
}

Write-Host 'OK: instalador encerra API antes de atualizar e preserva dados do cliente.' -ForegroundColor Green
