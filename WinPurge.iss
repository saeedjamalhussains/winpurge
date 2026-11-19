; WinPurge installer (Inno Setup 6.3 or newer). Built by build.bat, which passes
; /DAppVersion=x.y.z and, when signing is set up, /DSign and a sign tool named "wp"
; (which runs "build.bat sign <file>").
;
; Installs for the current user only: no administrator prompt, no Program Files.
; Adds a Start menu entry (and a Desktop shortcut if ticked), shows up in
; Settings > Apps > Installed apps, and starts WinPurge when it finishes.
;
; Upgrades are clean installs: if any WinPurge is already installed, Setup closes
; it, runs that version's own uninstaller silently, deletes its folder, then
; installs this version fresh. Settings, history and backups in %APPDATA% are
; kept, and so are the watcher and right-click menu if they were turned on.

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
OutputDir=dist
OutputBaseFilename=WinPurge-Setup-{#AppVersion}
SetupIconFile=build\assets\winpurge.ico
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
Source: "dist\WinPurge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
  { A silent uninstall is Setup replacing an older version: no questions. }
  if HasPrivacyChanges() and not UninstallSilent() then
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


{ ------------------------------------------------------------------ upgrades }

const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8F3C2A51-6D4E-4B8A-9E2F-5C1D7A3B9E40}_is1';
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  MenuKey = 'Software\Classes\exefile\shell\WinPurge.Uninstall';

var
  HadWatcher, HadMenu: Boolean;

{ Finds an installed WinPurge (per-user, or an older install for everyone). }
function FindPrevious(var Uninstaller, Folder, Version: String): Boolean;
var
  Roots: array[0..1] of Integer;
  I: Integer;
begin
  Result := False;
  Roots[0] := HKCU;
  Roots[1] := HKLM;
  for I := 0 to 1 do
    if RegQueryStringValue(Roots[I], UninstallKey, 'UninstallString', Uninstaller) then
    begin
      RegQueryStringValue(Roots[I], UninstallKey, 'InstallLocation', Folder);
      if not RegQueryStringValue(Roots[I], UninstallKey, 'DisplayVersion', Version) then
        Version := 'an earlier version';
      Uninstaller := RemoveQuotes(Uninstaller);
      if Folder = '' then
        Folder := ExtractFileDir(Uninstaller);
      Folder := RemoveBackslashUnlessRoot(Folder);
      Result := FileExists(Uninstaller);
      if Result then
        Exit;
    end;
end;

{ Shown on the "Ready to Install" page. }
function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
var
  Uninstaller, Folder, Version: String;
begin
  Result := '';
  if FindPrevious(Uninstaller, Folder, Version) then
    Result := 'WinPurge ' + Version + ' is installed.' + NewLine + Space +
              'Setup removes it first and installs {#AppVersion} fresh.' + NewLine + Space +
              'Your settings, cleaning history and backups are kept.' + NewLine + NewLine;
  if MemoTasksInfo <> '' then
    Result := Result + MemoTasksInfo;
end;

{ Runs before any file is copied: close WinPurge and remove the old version. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Uninstaller, Folder, Version: String;
  Code: Integer;
begin
  Result := '';
  HadWatcher := RegValueExists(HKCU, RunKey, 'WinPurge Watcher');
  HadMenu := RegKeyExists(HKCU, MenuKey);
  if not FindPrevious(Uninstaller, Folder, Version) then
    Exit;
  { Close the app and its background watcher so no file is in use. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM WinPurge.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  { "_?=" keeps the uninstaller in place so Setup can wait for it to finish. }
  if not Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART _?=' + AddQuotes(Folder), '', SW_HIDE,
              ewWaitUntilTerminated, Code) or (Code <> 0) then
  begin
    Result := 'Setup couldn''t remove WinPurge ' + Version + ' (code ' + IntToStr(Code) + ').' + #13#10 +
              'Uninstall it from Settings > Apps > Installed apps, then run Setup again.';
    Exit;
  end;
  { The in-place uninstaller can't delete itself, so remove what's left.
    Only a folder named WinPurge is ever deleted here. }
  if DirExists(Folder) and (CompareText(ExtractFileName(Folder), 'WinPurge') = 0) then
    DelTree(Folder, True, True, True);
end;

{ After installing: turn the watcher and right-click menu back on if they were on. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Parts: String;
  Code: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Parts := '';
  if HadWatcher then
    Parts := Parts + 'watch,';
  if HadMenu then
    Parts := Parts + 'menu,';
  if Parts <> '' then
    Exec(ExpandConstant('{app}\WinPurge.exe'), '--restore-integrations ' + Parts, '', SW_HIDE,
         ewWaitUntilTerminated, Code);
end;
