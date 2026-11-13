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
  #define VersaoApp "0.4.10"
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
Source: "..\build\dist\PrintGest\*"; DestDir: "{app}\PrintGest"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifndef ModoEstacao
Source: "..\build\dist\PrintGestAPI\*"; DestDir: "{app}\PrintGestAPI"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\pacote\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\{#NomeExibicao}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"
Name: "{group}\Desinstalar {#NomeExibicao}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomeExibicao}"; Filename: "{app}\PrintGest\PrintGest.exe"; WorkingDir: "{app}\PrintGest"; Tasks: icone_area_trabalho

[Run]
Filename: "{app}\PrintGest\PrintGest.exe"; Description: "Executar {#NomeExibicao}"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}\PrintGest"

#ifndef ModoEstacao
[UninstallRun]
; Para o desktop e o daemon - PostgreSQL removido (usa Neon)
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGest.exe /F"; Flags: runhidden; RunOnceId: "EncerraDesktop"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGestAPI.exe /F"; Flags: runhidden; RunOnceId: "EncerraAPI"

[UninstallDelete]
; Logs do backend
Type: filesandordirs; Name: "{app}\PrintGestAPI\logs"
Type: filesandordirs; Name: "{app}\PrintGestAPI"
#else
[UninstallDelete]
; Estacao: o .env com o endereco do servidor e gravado pelo assistente.
Type: files; Name: "{app}\PrintGest\.env"
#endif

[Code]
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
begin
  if CurStep = ssPostInstall then
  begin
    { .env ao lado do exe: o PrintGest le ao iniciar (modo Estacao). }
    SaveStringToFile(ExpandConstant('{app}\PrintGest\.env'),
      'PRINTGEST_API_URL=' + PaginaServidor.Values[0] + #13#10 +
      'PRINTGEST_MODO_ESTACAO=sim' + #13#10, False);
  end;
end;
#else
var
  PaginaTenant: TInputQueryWizardPage;

function CnpjValido(const Valor: String): Boolean;
var
  i: Integer;
begin
  Result := Length(Valor) = 14;
  if Result then
    for i := 1 to Length(Valor) do
      if not (Valor[i] in ['0'..'9']) then
      begin
        Result := False;
        Break;
      end;
end;

procedure InitializeWizard;
begin
  { Instalador UNIVERSAL (como Office/Corel): a identidade da gráfica é
    informada na instalação, não embutida no pacote. O .env embutido não tem
    CNPJ; o assistente grava o inquilino no .env da instalação. }
  PaginaTenant := CreateInputQueryPage(wpWelcome,
    'Gráfica (inquilino)',
    'Identifique a gráfica atendida por este servidor',
    'O mesmo instalador atende todas as gráficas. Informe o CNPJ da gráfica ' +
    '(como a chave de produto de um programa licenciado) — ele fica gravado ' +
    'no .env da instalação e define o inquilino dos dados.');
  PaginaTenant.Add('CNPJ da gráfica (14 dígitos):', False);
  PaginaTenant.Add('Razão social (opcional):', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PaginaTenant.ID then
  begin
    if not CnpjValido(Trim(PaginaTenant.Values[0])) then
    begin
      MsgBox('CNPJ inválido: informe os 14 dígitos, somente números.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Grava o inquilino no .env da instalação (o Local API Service le ao subir). }
    SaveStringToFile(ExpandConstant('{app}\PrintGestAPI\.env'),
      'PRINTGEST_EMPRESA_CNPJ=' + Trim(PaginaTenant.Values[0]) + #13#10 +
      'PRINTGEST_EMPRESA_RAZAO_SOCIAL=' + Trim(PaginaTenant.Values[1]) + #13#10,
      True);
  end;
end;
#endif
