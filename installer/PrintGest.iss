; PrintGest ERP - instalador Inno Setup.
;
; Instalacao por usuario (sem UAC): o PostgreSQL embarcado grava o cluster em
; {app}\postgres\data, entao a pasta do app precisa ser gravavel pelo usuario -
; por isso PrivilegesRequired=lowest com destino em {localappdata}\Programs.
; O desinstalador (unins000.exe) e gerado automaticamente e para o daemon e o
; banco antes de apagar os arquivos.
;
; Build: powershell -ExecutionPolicy Bypass -File scripts\empacotar.ps1

#ifndef VersaoApp
  #define VersaoApp "0.2.2"
#endif

#define NomeApp "PrintGest ERP"
#define Editora "PrintGest"

[Setup]
AppId={{9B3D4C0E-6D2A-4D47-8C11-3C79AB5F01A4}
AppName={#NomeApp}
AppVersion={#VersaoApp}
AppPublisher={#Editora}
DefaultDirName={localappdata}\Programs\PrintGest
DefaultGroupName={#NomeApp}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
; Caminho relativo ao diretorio do script (compilado via /O no empacotar.ps1)
OutputDir=..\dist_installer
OutputBaseFilename=PrintGest-Setup-{#VersaoApp}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#NomeApp}
UninstallDisplayIcon={app}\PrintGest\PrintGest.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "icone_area_trabalho"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
; Ordem importa para o [Run]: o backend e o PostgreSQL entram antes do atalho.
Source: "..\build\dist\PrintGest\*"; DestDir: "{app}\PrintGest"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\dist\PrintGestAPI\*"; DestDir: "{app}\PrintGestAPI"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\pacote\postgres\*"; DestDir: "{app}\postgres"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\pacote\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#NomeApp}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"
Name: "{group}\Desinstalar {#NomeApp}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomeApp}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"; Tasks: icone_area_trabalho

[Run]
Filename: "{app}\PrintGest\PrintGest.exe"; Description: "Executar {#NomeApp}"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}\PrintGest"

[UninstallRun]
; Para o desktop, o daemon e o PostgreSQL embarcado antes de apagar arquivos.
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGest.exe /F"; Flags: runhidden; RunOnceId: "EncerraDesktop"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGestAPI.exe /F"; Flags: runhidden; RunOnceId: "EncerraAPI"
Filename: "{app}\postgres\pgsql\bin\pg_ctl.exe"; Parameters: "stop -D ""{app}\postgres\data"" -m fast"; Flags: runhidden skipifdoesntexist; RunOnceId: "ParaPostgres"

[UninstallDelete]
; Gerados em runtime - nao estao em [Files] e precisam da limpeza explícita.
Type: filesandordirs; Name: "{app}\postgres\data"
Type: filesandordirs; Name: "{app}\PrintGestAPI\logs"
Type: files; Name: "{app}\postgres\postgres.log"
