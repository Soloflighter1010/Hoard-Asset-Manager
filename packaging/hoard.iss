; Hoard's Windows installer (Inno Setup 6). Built by .github/workflows/release.yml:
;   iscc /DAppVersion=2.4.2 packaging\hoard.iss   (after PyInstaller has made dist\Hoard)
;
; Installs for the current user only (no administrator prompt) into %LOCALAPPDATA%\Programs\Hoard, with a Start
; menu entry, an optional desktop icon and an uninstaller. Hoard's own data (settings, library, sign-ins, tags) is
; in %LOCALAPPDATA%\Hoard and downloads in the folder you chose: installing, updating and uninstalling never
; touch either.

#ifndef AppVersion
  #error Pass the version: iscc /DAppVersion=2.4.2 packaging\hoard.iss
#endif

[Setup]
; Fixed for every version, so a newer setup updates Hoard rather than installing it twice.
AppId={{E17FA814-69F9-5056-A999-C60F80574E31}
AppName=Hoard
AppVersion={#AppVersion}
AppVerName=Hoard {#AppVersion}
AppPublisher=SoloFlighter
AppPublisherURL=https://github.com/Soloflighter1010/Hoard-Asset-Manager
AppSupportURL=https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues
AppUpdatesURL=https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Hoard setup
PrivilegesRequired=lowest
DefaultDirName={autopf}\Hoard
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
SetupIconFile=hoard.ico
UninstallDisplayIcon={app}\Hoard.exe
UninstallDisplayName=Hoard
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Hoard-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
; Hoard running during an update is closed first (it quits cleanly: a download resumes next time).
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An update replaces the program files completely, so nothing from an older version is left behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Hoard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Hoard"; Filename: "{app}\Hoard.exe"; Comment: "Your VRChat asset library"
Name: "{autodesktop}\Hoard"; Filename: "{app}\Hoard.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Hoard.exe"; Description: "{cm:LaunchProgram,Hoard}"; Flags: nowait postinstall skipifsilent

[Code]
{ Hoard's window uses Microsoft Edge WebView2, part of Windows 11 and kept up to date on Windows 10. Without it,
  Hoard still works, in your web browser, so this only lets you know. }
function HasWebView2(): Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not HasWebView2()) and (not WizardSilent()) then
    MsgBox('Hoard''s window needs Microsoft Edge WebView2, which isn''t on this PC yet. Hoard will open in your web ' +
           'browser instead until it is. To get the window, install the "Evergreen Bootstrapper" from ' +
           'https://developer.microsoft.com/microsoft-edge/webview2/', mbInformation, MB_OK);
end;
