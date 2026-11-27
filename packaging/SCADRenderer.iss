#ifndef MyAppVersion
  #define MyAppVersion "1.3.0"
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
Name: "{group}\Удалить SCAD Renderer"; Filename: "{app}\unins000.exe"; IconFilename: "{app}\SCADRenderer.exe"; IconIndex: 0

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "install --quiet --target ""{app}"""; StatusMsg: "Регистрация SCAD Renderer..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "unregister --quiet --target ""{app}"""; RunOnceId: "UnregisterScadRenderer"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: dirifempty; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}\tray"
Type: dirifempty; Name: "{app}"

[Code]
var
  ExistingPage: TWizardPage;
  ReinstallRadio: TNewRadioButton;
  RemoveRadio: TNewRadioButton;
  Removing: Boolean;
  DeleteUserData: Boolean;
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
  RemovalForm := CreateCustomForm(ScaleX(320), ScaleY(130), False, True);
  try
    RemovalForm.ClientWidth := ScaleX(320);
    RemovalForm.ClientHeight := ScaleY(130);
    RemovalForm.Caption := 'SCAD Renderer';
    RemovalText := TNewStaticText.Create(RemovalForm);
    RemovalText.Parent := RemovalForm;
    RemovalText.Left := ScaleX(16);
    RemovalText.Top := ScaleY(16);
    RemovalText.Width := RemovalForm.ClientWidth - ScaleX(32);
    RemovalText.Height := ScaleY(54);
    RemovalText.WordWrap := True;
    RemovalText.Caption := 'SCAD Renderer удалён.' + #13#10 +
      'Окно закроется через 10 сек.';

    CloseButton := TNewButton.Create(RemovalForm);
    CloseButton.Parent := RemovalForm;
    CloseButton.Caption := 'Закрыть';
    CloseButton.Width := ScaleX(90);
    CloseButton.Height := ScaleY(24);
    CloseButton.Left := RemovalForm.ClientWidth - CloseButton.Width - ScaleX(16);
    CloseButton.Top := RemovalForm.ClientHeight - CloseButton.Height - ScaleY(14);
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

function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Note: TNewStaticText;
  DataCheck: TNewCheckBox;
  DeleteButton: TNewButton;
  CancelButton: TNewButton;
begin
  DeleteUserData := True;
  if UninstallSilent then
  begin
    Result := True;
    Exit;
  end;

  Form := CreateCustomForm(ScaleX(420), ScaleY(185), False, True);
  try
    Form.ClientWidth := ScaleX(420);
    Form.ClientHeight := ScaleY(185);
    Form.Caption := 'Удаление SCAD Renderer';

    Note := TNewStaticText.Create(Form);
    Note.Parent := Form;
    Note.Left := ScaleX(16);
    Note.Top := ScaleY(14);
    Note.Width := Form.ClientWidth - ScaleX(32);
    Note.Height := ScaleY(44);
    Note.WordWrap := True;
    Note.Caption := 'Будут удалены настройки, журналы и профиль браузера.' + #13#10 + 'Слоты в slicer-slots сохранятся.';

    DataCheck := TNewCheckBox.Create(Form);
    DataCheck.Parent := Form;
    DataCheck.Left := ScaleX(16);
    DataCheck.Top := ScaleY(66);
    DataCheck.Width := Form.ClientWidth - ScaleX(32);
    DataCheck.Height := ScaleY(38);
    DataCheck.Caption := 'Удалить также настройки, журналы и профиль браузера';
    DataCheck.Checked := True;

    DeleteButton := TNewButton.Create(Form);
    DeleteButton.Parent := Form;
    DeleteButton.Caption := 'Удалить';
    DeleteButton.Width := ScaleX(95);
    DeleteButton.Height := ScaleY(25);
    DeleteButton.Left := Form.ClientWidth - DeleteButton.Width - ScaleX(16);
    DeleteButton.Top := Form.ClientHeight - DeleteButton.Height - ScaleY(14);
    DeleteButton.ModalResult := mrOk;
    DeleteButton.Default := True;

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Отмена';
    CancelButton.Width := ScaleX(95);
    CancelButton.Height := ScaleY(25);
    CancelButton.Left := DeleteButton.Left - CancelButton.Width - ScaleX(8);
    CancelButton.Top := DeleteButton.Top;
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;

    if Form.ShowModal = mrOk then
    begin
      DeleteUserData := DataCheck.Checked;
      Result := True;
    end
    else
      Result := False;
  finally
    Form.Free;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if DeleteUserData then
    begin
      DelTree(ExpandConstant('{app}\scad-drop\state'), True, True, True);
      DelTree(ExpandConstant('{app}\scad-variants\state'), True, True, True);
      DelTree(ExpandConstant('{app}\tray\state'), True, True, True);
      RemoveDir(ExpandConstant('{app}\scad-drop'));
      RemoveDir(ExpandConstant('{app}\scad-variants'));
      RemoveDir(ExpandConstant('{app}\_internal'));
      RemoveDir(ExpandConstant('{app}\tray'));
      { The uninstaller itself still lives in the application folder; remove
        the empty shell after it has exited. }
      Exec(
        ExpandConstant('{cmd}'),
        '/c ping -n 4 127.0.0.1 >nul & rmdir /s /q "' +
          ExpandConstant('{app}') + '"',
        '',
        SW_HIDE,
        ewNoWait,
        ResultCode
      );
    end;
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

