#ifndef MyAppVersion
  #define MyAppVersion "1.2.0-dev.8"
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
DisableDirPage=no
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
UsePreviousAppDir=yes
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
Filename: "{app}\{#MyAppExeName}"; Parameters: "install --quiet --target ""{app}"""; StatusMsg: "Регистрация SCAD Renderer..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "unregister --quiet --target ""{app}"""; RunOnceId: "UnregisterScadRenderer"; Flags: runhidden waituntilterminated

[Code]
var
  ExistingPage: TWizardPage;
  ReinstallRadio: TNewRadioButton;
  RemoveRadio: TNewRadioButton;
  Removing: Boolean;
  RemovalForm: TSetupForm;
  RemovalText: TNewStaticText;
  RemovalTimer: Longword;
  RemovalSeconds: Integer;

function SetTimer(hWnd, nIDEvent, uElapse, lpTimerFunc: Longword): Longword;
external 'SetTimer@user32.dll stdcall';

function KillTimer(hWnd, nIDEvent: Longword): Bool;
external 'KillTimer@user32.dll stdcall';

function GetInstallDir: String;
begin
  Result := WizardForm.DirEdit.Text;
  if Result = '' then
    Result := ExpandConstant('{localappdata}\Programs\SCADRenderer');
end;

function IsInstalled: Boolean;
begin
  Result := FileExists(AddBackslash(GetInstallDir) + 'SCADRenderer.exe');
end;

procedure RemovalTimerProc(Arg1, Arg2, Arg3, Arg4: Longword);
begin
  if RemovalForm = nil then
    Exit;
  Dec(RemovalSeconds);
  if RemovalSeconds <= 0 then
  begin
    if RemovalTimer <> 0 then
    begin
      KillTimer(0, RemovalTimer);
      RemovalTimer := 0;
    end;
    RemovalForm.Close;
  end
  else
    RemovalText.Caption := 'SCAD Renderer удалён.' + #13#10 +
      'Окно закроется через ' + IntToStr(RemovalSeconds) + ' сек.';
end;

procedure ShowRemovalComplete;
var
  CloseButton: TNewButton;
begin
  RemovalSeconds := 10;
  RemovalForm := CreateCustomForm(ScaleX(440), ScaleY(150), False, True);
  try
    RemovalForm.Caption := 'SCAD Renderer';
    RemovalText := TNewStaticText.Create(RemovalForm);
    RemovalText.Parent := RemovalForm;
    RemovalText.Left := ScaleX(18);
    RemovalText.Top := ScaleY(20);
    RemovalText.Width := RemovalForm.ClientWidth - ScaleX(36);
    RemovalText.Height := ScaleY(70);
    RemovalText.WordWrap := True;
    RemovalText.Caption := 'SCAD Renderer удалён.' + #13#10 +
      'Окно закроется через 10 сек.';

    CloseButton := TNewButton.Create(RemovalForm);
    CloseButton.Parent := RemovalForm;
    CloseButton.Caption := 'Закрыть';
    CloseButton.Width := ScaleX(95);
    CloseButton.Height := ScaleY(25);
    CloseButton.Left := RemovalForm.ClientWidth - CloseButton.Width - ScaleX(18);
    CloseButton.Top := RemovalForm.ClientHeight - CloseButton.Height - ScaleY(16);
    CloseButton.ModalResult := mrOk;
    CloseButton.Default := True;

    RemovalTimer := SetTimer(0, 0, 1000, CreateCallback(@RemovalTimerProc));
    RemovalForm.ShowModal;
  finally
    if RemovalTimer <> 0 then
    begin
      KillTimer(0, RemovalTimer);
      RemovalTimer := 0;
    end;
    RemovalForm.Free;
    RemovalForm := nil;
  end;
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

  Uninstaller := AddBackslash(GetInstallDir) + 'unins000.exe';
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
  else if FileExists(AddBackslash(GetInstallDir) + 'SCADRenderer.exe') then
  begin
    Exec(
      AddBackslash(GetInstallDir) + 'SCADRenderer.exe',
      'uninstall --quiet --target "' + GetInstallDir + '"',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;

  Result := False;
  Removing := True;
  ShowRemovalComplete;
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

