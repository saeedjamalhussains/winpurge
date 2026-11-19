; WinPurge installer (Inno Setup 6.3 or newer). Built by build.bat, which passes
; /DAppVersion=x.y.z and, when signing is set up, /DSign and a sign tool named "wp".
;
; Installs for the current user only: no administrator prompt, no Program Files.
; Adds a Start menu entry (and a Desktop shortcut if ticked), shows up in
; Settings > Apps > Installed apps, and starts WinPurge when it finishes.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2A51-6D4E-4B8A-9E2F-5C1D7A3B9E40}
AppName=WinPurge
AppVersion={#AppVersion}
AppVerName=WinPurge {#AppVersion}
AppPublisher=WinPurge
AppComments=App uninstaller, junk cleaner and privacy settings for Windows
DefaultDirName={autopf}\WinPurge
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WinPurge-Setup-{#AppVersion}
SetupIconFile=..\assets\winpurge.ico
UninstallDisplayIcon={app}\WinPurge.exe
UninstallDisplayName=WinPurge
WizardStyle=modern
WizardSizePercent=110
Compression=lzma2/max
SolidCompression=yes
MinVersion=10.0
CloseApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName=WinPurge
VersionInfoDescription=WinPurge Setup
#ifdef Sign
SignTool=wp
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Add a shortcut to the &Desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\WinPurge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\WinPurge"; Filename: "{app}\WinPurge.exe"; AppUserModelID: "WinPurge.App"
Name: "{autodesktop}\WinPurge"; Filename: "{app}\WinPurge.exe"; Tasks: desktopicon; AppUserModelID: "WinPurge.App"

[Run]
Filename: "{app}\WinPurge.exe"; Description: "Start WinPurge"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Turn off the uninstall watcher and the right-click menu item before removing files.
Filename: "{app}\WinPurge.exe"; Parameters: "--remove-integrations"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveIntegrations"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
{ True when WinPurge changed privacy settings that haven't been restored. }
function HasPrivacyChanges(): Boolean;
var
  Text: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{userappdata}\WinPurge\privacy-backup.json'), Text) and
            ((Pos('"hive"', Text) > 0) or (Pos('DiagTrack', Text) > 0));
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if HasPrivacyChanges() then
    Result := MsgBox('WinPurge changed some Windows privacy settings, and they stay changed after it''s removed.' + #13#10#13#10 +
                     'To put them back first, choose No, open WinPurge and press Restore originals on the Privacy page.' + #13#10#13#10 +
                     'Uninstall WinPurge now?', mbConfirmation, MB_YESNO) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent() then
    if MsgBox('Also remove WinPurge''s settings, cleaning history and logs?' + #13#10#13#10 +
              'Backups of privacy and registry settings are kept either way.', mbConfirmation, MB_YESNO) = IDYES then
    begin
      DeleteFile(ExpandConstant('{userappdata}\WinPurge\settings.json'));
      DeleteFile(ExpandConstant('{userappdata}\WinPurge\ignored.json'));
      DeleteFile(ExpandConstant('{userappdata}\WinPurge\history.json'));
      DelTree(ExpandConstant('{localappdata}\WinPurge'), True, True, True);
    end;
end;
