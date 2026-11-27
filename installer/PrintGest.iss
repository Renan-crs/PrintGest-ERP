; PrintGest ERP - instalador Inno Setup (modo Servidor ou Estacao).
;
; SERVIDOR (padrao): desktop + Local API Service + Neon Database.
;   powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1
; ESTACAO: apenas o desktop; o assistente pergunta o ENDERECO do servidor e
;   grava um .env ao lado do PrintGest.exe (PRINTGEST_API_URL). Instalacao
;   por usuario (sem UAC), com desinstalador.
;   powershell ... -File scripts\empacotar.ps1 -Modo estacao
;
; As duas instalacoes convivem na mesma maquina (AppIds e pastas distintos).

#ifndef VersaoApp
  #define VersaoApp "0.5.45"
#endif

#define NomeApp "PrintGest ERP"
#define Editora "PrintGest"

#ifdef ModoEstacao
  #define SufixoModo "Estacao"
  #define NomeExibicao "PrintGest ERP Estacao"
#else
  #define SufixoModo ""
  #define NomeExibicao NomeApp
#endif

[Setup]
#ifdef ModoEstacao
AppId={{5E9B02D4-1F65-4A19-9BD8-C8E9D0C40E41}
DefaultDirName={localappdata}\Programs\PrintGestEstacao
DefaultGroupName=PrintGest ERP Estacao
#else
AppId={{9B3D4C0E-6D2A-4D47-8C11-3C79AB5F01A4}
DefaultDirName={localappdata}\Programs\PrintGest
DefaultGroupName=PrintGest ERP
#endif
AppName={#NomeExibicao}
AppVersion={#VersaoApp}
AppPublisher={#Editora}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#NomeExibicao}
UninstallDisplayIcon={app}\PrintGest\PrintGest.exe
SetupIconFile=..\desktop\printgest\ui\assets\printgest.ico
; Caminho relativo ao diretorio do script (compilado via /O no empacotar.ps1)
OutputDir=..\dist_installer
OutputBaseFilename=PrintGest-Setup-{#VersaoApp}{#SufixoModo}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "icone_area_trabalho"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
; Desktop para ambos os modos; backend apenas para Servidor.
; PostgreSQL REMOVIDO - usando Neon em nuvem (v0.3.4)
; NUNCA distribuir dados do cliente: .env (tenant/credenciais locais), cofres
; cifrados (licenca.dat/integracoes.dat) e dumps ficam FORA do pacote.
; `ignoreversion` preserva o que já existe quando o arquivo é idêntico.
Source: "..\build\dist\PrintGest\*"; DestDir: "{app}\PrintGest"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.env,.env.*,*.dat,*.dump,*.log,backups\*"
#ifndef ModoEstacao
Source: "..\build\dist\PrintGestAPI\*"; DestDir: "{app}\PrintGestAPI"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.env,.env.*,*.dat,*.dump,*.log,backups\*,logs\*"
Source: "..\build\pacote\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
#endif
; Licenças e avisos de terceiros — devem acompanhar toda redistribuição.
Source: "..\LICENSE"; DestDir: "{app}\Licencas"; Flags: ignoreversion
Source: "..\LICENSE-APACHE-2.0"; DestDir: "{app}\Licencas"; Flags: ignoreversion
Source: "..\LICENSE-COMMERCIAL.md"; DestDir: "{app}\Licencas"; Flags: ignoreversion
Source: "..\LICENCIAMENTO.md"; DestDir: "{app}\Licencas"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}\Licencas"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}\Licencas"; Flags: ignoreversion

[Icons]
Name: "{group}\{#NomeExibicao}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"
Name: "{group}\Desinstalar {#NomeExibicao}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomeExibicao}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"; Tasks: icone_area_trabalho

[Run]
; Sem `skipifsilent`: na atualização silenciosa (Fase 2) o app é reaberto.
Filename: "{app}\PrintGest\PrintGest.exe"; Description: "Executar {#NomeExibicao}"; Flags: nowait postinstall; WorkingDir: "{app}\PrintGest"

#ifndef ModoEstacao
[UninstallRun]
; Para o desktop e o daemon - PostgreSQL removido (usa Neon)
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGest.exe /F"; Flags: runhidden; RunOnceId: "EncerraDesktop"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGestAPI.exe /F"; Flags: runhidden; RunOnceId: "EncerraAPI"

[UninstallDelete]
; Logs do backend (úteis para suporte, mas descartáveis na desinstalação).
Type: filesandordirs; Name: "{app}\PrintGestAPI\logs"
; Os binários instalados são removidos pelo próprio Inno Setup. Não há
; "filesandordirs" para {app}\PrintGestAPI: arquivos criados em runtime
; (.env com o tenant, cofres *.dat, dumps e backups) NÃO são apagados na
; desinstalação nem na atualização — nenhuma versão perde dados do cliente.
#else
[UninstallDelete]
; Estacao: o .env com o endereco do servidor e gravado pelo assistente.
Type: files; Name: "{app}\PrintGest\.env"
#endif

[Code]
{ ---------------------------------------------------------------------------
  Atualização segura (PRD v3.3): ao instalar uma versão MAIS NOVA sobre uma
  instalação existente, o Local API Service e o desktop DEVEM ser encerrados
  antes de substituir os binários — arquivos .exe/.dll em uso não podem ser
  sobrescritos no Windows. Os dados do cliente NUNCA são apagados: esta função
  apenas fecha processos; não toca em .env, cofres, banco ou backups.
  --------------------------------------------------------------------------- }
procedure EncerrarProcesso(const Nome: string);
var
  Codigo: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'),
    '/IM ' + Nome + ' /F', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  { A existência do exe indica atualização sobre instalação anterior —
    primeira instalação não tem processo para encerrar. }
  if FileExists(ExpandConstant('{app}\PrintGest\PrintGest.exe')) then
  begin
    EncerrarProcesso('PrintGestAPI.exe');
    EncerrarProcesso('PrintGest.exe');
    Log('PrintGest: processos encerrados antes da atualização para ' + '{#VersaoApp}' + '. Dados preservados.');
  end;
end;

#ifdef ModoEstacao
var
  PaginaServidor: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  PaginaServidor := CreateInputQueryPage(wpWelcome,
    'Servidor da gráfica',
    'Endereço do servidor PrintGest',
    'Informe o endereço da máquina servidora — por exemplo, 192.168.0.10:8000.' +
    ' Você pode trocar depois, dentro do programa.');
  PaginaServidor.Add('Endereço do servidor:', False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath: String;
  Endereco: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  EnvPath := ExpandConstant('{app}\PrintGest\.env');
  Endereco := PaginaServidor.Values[0];

  { Atualizacao silenciosa (Fase 2): a pagina nao aparece, entao Endereco vem
    vazio. NUNCA sobrescrever um .env existente — isso apagaria o endereco do
    servidor da grafica. Instalacao nova sem .env segue gravando o padrao. }
  if (Endereco = '') and FileExists(EnvPath) then
  begin
    Log('PrintGest: atualizacao silenciosa - preservando .env da estacao.');
    Exit;
  end;

  SaveStringToFile(EnvPath,
    'PRINTGEST_API_URL=' + Endereco + #13#10 +
    'PRINTGEST_MODO_ESTACAO=sim' + #13#10, False);
end;
#endif
