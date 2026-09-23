; Inno Setup Script for InboxIQ
; Produces a standalone, single-file Windows installer: InboxIQ-Setup.exe

#define MyAppName "InboxIQ"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "InboxIQ"
#define MyAppURL "https://github.com/omkanekar28/InboxIQ"
#define MyAppExeName "InboxIQ.exe"

[Setup]
AppId={{E68A0B2C-9C4E-4B7E-9714-38F6F4C4702D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
DefaultGroupName={#MyAppName}
OutputDir=dist-installer
OutputBaseFilename=InboxIQ-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\InboxIQ\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Silently terminate running instances of InboxIQ or llama-server if still open
  Exec('taskkill.exe', '/F /IM InboxIQ.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('taskkill.exe', '/F /IM llama-server.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyAppName}');
    if DirExists(DataDir) then
    begin
      if not UninstallSilent then
      begin
        if MsgBox('Do you want to delete all InboxIQ user data and settings?' #13#10#13#10 +
                  'This will permanently remove:' #13#10 +
                  '  - Downloaded AI Models (~5 GB)' #13#10 +
                  '  - Local Indexed Email Database' #13#10 +
                  '  - Gmail OAuth Credentials & Tokens' #13#10 +
                  '  - Application Logs' #13#10#13#10 +
                  'Location: ' + DataDir + #13#10#13#10 +
                  'Click ''Yes'' to completely remove all data, or ''No'' to keep it.',
                  mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        begin
          DelTree(DataDir, True, True, True);
        end;
      end;
    end;
  end;
end;

