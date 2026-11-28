; PrintGest ERP - instalador UNICO (Servidor ou Estacao escolhidos no wizard).
;
; Na instalacao o operador escolhe:
;   SERVIDOR: desktop + Local API Service + .env do Neon (credenciais gravadas
;             somente neste modo). Atende as estacoes da rede da grafica.
;   ESTACAO:  apenas o desktop; o assistente pede o endereco do servidor e
;             grava PRINTGEST_API_URL / PRINTGEST_MODO_ESTACAO no .env do
;             desktop. Nenhuma credencial do backend e gravada.
;
; Instalacao por usuario (sem UAC), com desinstalador e dados preservados.
; Powershell de build: scripts\empacotar.ps1 (sem -Modo).

#ifndef VersaoApp
  #define VersaoApp "0.5.47"
#endif

#define NomeApp "PrintGest ERP"
#define Editora "PrintGest"
#define NomeExibicao NomeApp

[Setup]
; AppId e pasta do antigo pacote Servidor: atualizacoes sobre servidor mantem
; a identidade. Maquinas com o antigo pacote Estacao devem desinstalar antes.
AppId={{9B3D4C0E-6D2A-4D47-8C11-3C79AB5F01A4}
DefaultDirName={localappdata}\Programs\PrintGest
DefaultGroupName=PrintGest ERP
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
OutputBaseFilename=PrintGest-Setup-{#VersaoApp}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "icone_area_trabalho"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"

[Files]
; Os DOIS binarios viajam no Setup; a decisao de gravar credenciais e do wizard.
; PostgreSQL REMOVIDO - usando Neon em nuvem (v0.3.4)
; NUNCA distribuir dados do cliente: .env (tenant/credenciais locais), cofres
; cifrados (licenca.dat/integracoes.dat) e dumps ficam FORA do pacote.
; `ignoreversion` preserva o que ja existe quando o arquivo e identico.
Source: "..\build\dist\PrintGest\*"; DestDir: "{app}\PrintGest"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.env,.env.*,*.dat,*.dump,*.log,backups\*"
Source: "..\build\dist\PrintGestAPI\*"; DestDir: "{app}\PrintGestAPI"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.env,.env.*,*.dat,*.dump,*.log,backups\*,logs\*"
; Template de configuracao do servidor: removido do disco ao final da instalacao
; em AMBOS os modos. So e copiado para .env se o operador escolher Servidor.
Source: "..\build\pacote\config-servidor.txt"; DestDir: "{app}\PrintGestAPI"; Flags: ignoreversion
Source: "..\build\pacote\LEIA-ME.txt"; DestDir: "{app}"; Flags: ignoreversion
; Licencas e avisos de terceiros - devem acompanhar toda redistribuicao.
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
; Sem `skipifsilent`: na atualizacao silenciosa (Fase 2) o app e reaberto.
Filename: "{app}\PrintGest\PrintGest.exe"; Description: "Executar {#NomeExibicao}"; Flags: nowait postinstall; WorkingDir: "{app}\PrintGest"

[UninstallRun]
; Para o desktop e o daemon - PostgreSQL removido (usa Neon)
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGest.exe /F"; Flags: runhidden; RunOnceId: "EncerraDesktop"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM PrintGestAPI.exe /F"; Flags: runhidden; RunOnceId: "EncerraAPI"

[UninstallDelete]
; Logs do backend (uteis para suporte, mas descartaveis na desinstalacao).
Type: filesandordirs; Name: "{app}\PrintGestAPI\logs"
; Marcador de modo e configuracao de estacao (nao sao dados do cliente).
Type: files; Name: "{app}\modo.txt"
Type: files; Name: "{app}\PrintGest\.env"
; Os binarios instalados sao removidos pelo proprio Inno Setup. Nao ha
; "filesandordirs" para {app}\PrintGestAPI: arquivos criados em runtime
; (.env do servidor, cofres *.dat, dumps e backups) NAO sao apagados na
; desinstalacao nem na atualizacao — nenhuma versao perde dados do cliente.

[Code]
{ ---------------------------------------------------------------------------
  Atualizacao segura (PRD v3.3): ao instalar uma versao MAIS NOVA sobre uma
  instalacao existente, o Local API Service e o desktop DEVEM ser encerrados
  antes de substituir os binarios — arquivos .exe/.dll em uso nao podem ser
  sobrescritos no Windows. Os dados do cliente NUNCA sao apagados: esta funcao
  apenas fecha processos; nao toca em .env, cofres, banco ou backups.
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
  { A existencia do exe indica atualizacao sobre instalacao anterior —
    primeira instalacao nao tem processo para encerrar. }
  if FileExists(ExpandConstant('{app}\PrintGest\PrintGest.exe')) then
  begin
    EncerrarProcesso('PrintGestAPI.exe');
    EncerrarProcesso('PrintGest.exe');
    Log('PrintGest: processos encerrados antes da atualizacao para ' + '{#VersaoApp}' + '. Dados preservados.');
  end;
end;

{ ---------------------------------------------------------------------------
  Pagina unica de modo. Em atualizacao silenciosa (/VERYSILENT) a pagina nao
  aparece: o modo e inferido do marcador deixado pela instalacao anterior.
  --------------------------------------------------------------------------- }
var
  PaginaModo: TWizardPage;
  RbServidor: TRadioButton;
  RbEstacao: TRadioButton;
  LblEndereco: TLabel;
  EdEndereco: TEdit;
  ModoEstacaoFinal: Boolean;

function ModoEstacaoInstalado: Boolean;
var
  Marcador: AnsiString;
begin
  Result := False;
  if FileExists(ExpandConstant('{app}\modo.txt')) then
  begin
    if LoadStringFromFile(ExpandConstant('{app}\modo.txt'), Marcador) then
      Result := Trim(Marcador) = 'estacao';
    Exit;
  end;
  { Instalacao legada sem marcador: .env de estacao sem daemon local. }
  Result := FileExists(ExpandConstant('{app}\PrintGest\.env')) and
    (not FileExists(ExpandConstant('{app}\PrintGestAPI\PrintGestAPI.exe')));
end;

procedure ModoClick(Sender: TObject);
begin
  EdEndereco.Enabled := RbEstacao.Checked;
  LblEndereco.Enabled := RbEstacao.Checked;
end;

procedure InitializeWizard;
var
  Painel: TPanel;
  Topo: Integer;
begin
  PaginaModo := CreateCustomPage(wpWelcome, 'Tipo de instalacao',
    'Como este computador sera usado?');

  Painel := TPanel.Create(PaginaModo);
  Painel.Parent := PaginaModo.Surface;
  Painel.SetBounds(0, 0, PaginaModo.Surface.Width, 170);
  Painel.BevelOuter := bvNone;

  RbServidor := TRadioButton.Create(Painel);
  RbServidor.Parent := Painel;
  RbServidor.SetBounds(10, 10, Painel.Width - 20, 22);
  RbServidor.Caption := 'Servidor — guarda a licenca e atende os outros computadores';
  RbServidor.Checked := not WizardSilent;
  RbServidor.OnClick := @ModoClick;

  RbEstacao := TRadioButton.Create(Painel);
  RbEstacao.Parent := Painel;
  RbEstacao.SetBounds(10, 40, Painel.Width - 20, 22);
  RbEstacao.Caption := 'Estacao — conecta ao servidor da grafica';
  RbEstacao.Checked := WizardSilent and ModoEstacaoInstalado;
  RbEstacao.OnClick := @ModoClick;

  Topo := 80;
  LblEndereco := TLabel.Create(Painel);
  LblEndereco.Parent := Painel;
  LblEndereco.SetBounds(10, Topo, Painel.Width - 20, 20);
  LblEndereco.Caption := 'Endereco do servidor (ex.: 192.168.0.10:8000)';

  EdEndereco := TEdit.Create(Painel);
  EdEndereco.Parent := Painel;
  EdEndereco.SetBounds(10, Topo + 24, 320, 23);
  EdEndereco.Text := '';

  ModoClick(nil);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvPath: String;
  EnvApiPath: String;
  Template: String;
  Conteudo: AnsiString;
  Endereco: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  if WizardSilent then
    ModoEstacaoFinal := ModoEstacaoInstalado
  else
    ModoEstacaoFinal := RbEstacao.Checked;

  { Marcador para preservar o modo nas proximas atualizacoes silenciosas. }
  if ModoEstacaoFinal then
    SaveStringToFile(ExpandConstant('{app}\modo.txt'), 'estacao', False)
  else
    SaveStringToFile(ExpandConstant('{app}\modo.txt'), 'servidor', False);

  { O template de credenciais NUNCA permanece no disco, em nenhum dos modos. }
  Template := ExpandConstant('{app}\PrintGestAPI\config-servidor.txt');
  EnvApiPath := ExpandConstant('{app}\PrintGestAPI\.env');
  EnvPath := ExpandConstant('{app}\PrintGest\.env');

  if ModoEstacaoFinal then
  begin
    if FileExists(Template) then
      DeleteFile(Template);

    Endereco := Trim(EdEndereco.Text);

    { Atualizacao silenciosa (Fase 2): a pagina nao aparece, entao Endereco vem
      vazio. NUNCA sobrescrever um .env existente — isso apagaria o endereco do
      servidor da grafica. Instalacao nova sem .env segue gravando o padrao. }
    if (Endereco = '') and FileExists(EnvPath) then
    begin
      Log('PrintGest: atualizacao silenciosa - preservando .env da estacao.');
      Exit;
    end;

    if Endereco = '' then
      Endereco := '127.0.0.1:8000';

    SaveStringToFile(EnvPath,
      'PRINTGEST_API_URL=' + Endereco + #13#10 +
      'PRINTGEST_MODO_ESTACAO=sim' + #13#10, False);
  end
  else
  begin
    { Servidor: credenciais gravadas SOMENTE aqui, e nunca sobre um .env
      existente (atualizacao preserva tenant/credenciais ajustadas). }
    if FileExists(Template) then
    begin
      if (not FileExists(EnvApiPath)) and
         LoadStringFromFile(Template, Conteudo) then
        SaveStringToFile(EnvApiPath, Conteudo, False);
      DeleteFile(Template);
    end;

    { Troca de estacao legada para servidor: remove o .env da estacao. }
    if (not WizardSilent) and FileExists(EnvPath) then
      DeleteFile(EnvPath);
  end;
end;
