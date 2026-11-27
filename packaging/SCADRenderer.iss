#ifndef MyAppVersion
  #define MyAppVersion "1.2.0-dev.7"
#endif

#define MyAppName "SCAD Renderer"
#define MyAppPublisher "akork"
#define MyAppURL "https://github.com/akork/scad-renderer"
#define MyAppExeName "SCADRenderer.exe"
#define ReleaseDir "..\release\SCADRenderer-" + MyAppVersion + "-win64"

[Setup]
AppId={{8E6C9F1A-4B7D-4C61-9A8E-2D5B3F7C1A90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\SCADRenderer
DefaultGroupName={#MyAppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=SCADRendererSetup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
UsePreviousAppDir=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\SCAD Render"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\tray\tray-launch.vbs"""; WorkingDir: "{app}\tray"; IconFilename: "{sys}\shell32.dll"; IconIndex: 3; Tasks: desktopicon
Name: "{group}\Удалить SCAD Renderer"; Filename: "{app}\unins000.exe"; Parameters: "/VERYSILENT"; IconFilename: "{app}\SCADRenderer.exe"; IconIndex: 0

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "install --quiet"; StatusMsg: "Регистрация SCAD Renderer..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "unregister --quiet"; RunOnceId: "UnregisterScadRenderer"; Flags: runhidden waituntilterminated

[Code]
var
  ExistingPage: TWizardPage;
  ReinstallRadio: TNewRadioButton;
  RemoveRadio: TNewRadioButton;
  Removing: Boolean;

function IsInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\SCADRenderer\SCADRenderer.exe'));
end;

procedure InitializeWizard;
begin
  if not IsInstalled then
    Exit;

  ExistingPage := CreateCustomPage(
    wpWelcome,
    'SCAD Renderer уже установлен',
    'Выберите, что сделать с существующей установкой.'
  );

  ReinstallRadio := TNewRadioButton.Create(ExistingPage);
  ReinstallRadio.Parent := ExistingPage.Surface;
  ReinstallRadio.Caption := 'Переустановить SCAD Renderer';
  ReinstallRadio.Left := ScaleX(0);
  ReinstallRadio.Top := ScaleY(8);
  ReinstallRadio.Width := ExistingPage.Surface.Width - ScaleX(8);
  ReinstallRadio.Height := ScaleY(21);
  ReinstallRadio.Checked := True;

  RemoveRadio := TNewRadioButton.Create(ExistingPage);
  RemoveRadio.Parent := ExistingPage.Surface;
  RemoveRadio.Caption := 'Удалить SCAD Renderer';
  RemoveRadio.Left := ScaleX(0);
  RemoveRadio.Top := ScaleY(40);
  RemoveRadio.Width := ExistingPage.Surface.Width - ScaleX(8);
  RemoveRadio.Height := ScaleY(21);
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if Removing then
    Confirm := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
  Uninstaller: String;
begin
  Result := True;
  if (ExistingPage = nil) or (CurPageID <> ExistingPage.ID) then
    Exit;
  if not RemoveRadio.Checked then
    Exit;

  if MsgBox('Удалить SCAD Renderer?', mbConfirmation, MB_YESNO) <> IDYES then
  begin
    Result := False;
    Exit;
  end;

  Uninstaller := ExpandConstant('{localappdata}\Programs\SCADRenderer\unins000.exe');
  if FileExists(Uninstaller) then
  begin
    if not Exec(
      Uninstaller,
      '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
      '',
      SW_SHOW,
      ewWaitUntilTerminated,
      ResultCode
    ) then
    begin
      MsgBox('Не удалось запустить удаление.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end
  else if FileExists(ExpandConstant('{localappdata}\Programs\SCADRenderer\SCADRenderer.exe')) then
  begin
    Exec(
      ExpandConstant('{localappdata}\Programs\SCADRenderer\SCADRenderer.exe'),
      'uninstall --quiet',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;

  Result := False;
  Removing := True;
  WizardForm.Close;
end;

procedure StopOldApp;
var
  ResultCode: Integer;
begin
  { The gallery server and a running SCADRenderer.exe lock DLLs under _internal. }
  Exec(
    ExpandConstant('{cmd}'),
    '/c taskkill /F /IM SCADRenderer.exe /T',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  Sleep(1200);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopOldApp;
end;

