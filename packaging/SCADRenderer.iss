#ifndef MyAppVersion
  #define MyAppVersion "1.2.0-dev.5"
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

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "install --quiet"; StatusMsg: "Регистрация SCAD Renderer..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "unregister --quiet"; RunOnceId: "UnregisterScadRenderer"; Flags: runhidden waituntilterminated

[Code]
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

