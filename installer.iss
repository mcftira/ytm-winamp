; ytm-winamp installer — Inno Setup script.
; Builds ytm-winamp-setup.exe: a proper wizard that installs the app,
; the portable tools, Winamp (via winget), shortcuts, and the theme.

#define AppName "ytm-winamp"
#define AppVersion "0.8.0"
#define AppPublisher "mcftira"
#define AppURL "https://github.com/mcftira/ytm-winamp"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\ytm-winamp
DefaultGroupName={#AppName}
OutputDir=installer
OutputBaseFilename=ytm-winamp-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\ytm-winamp.exe
LicenseFile=LICENSE
VersionInfoVersion={#AppVersion}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\ytm-winamp.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\tools\yt-dlp.exe"; DestDir: "{%USERPROFILE}\.ytm-winamp\bin"; Flags: ignoreversion
Source: "dist\tools\ffmpeg.exe"; DestDir: "{%USERPROFILE}\.ytm-winamp\bin"; Flags: ignoreversion

[Icons]
Name: "{group}\Play the era radio"; Filename: "{app}\ytm-winamp.exe"; Parameters: "era"; Comment: "Start the 1995-2005 hits radio in Winamp"
Name: "{group}\ytm-winamp terminal"; Filename: "{app}\ytm-winamp.exe"; Comment: "All commands: play, search, liked, era, serve"
Name: "{autodesktop}\ytm-winamp era radio"; Filename: "{app}\ytm-winamp.exe"; Parameters: "era"; Tasks: desktopicon

[Run]
Filename: "winget"; Parameters: "install --id Winamp.Winamp -e --accept-package-agreements --accept-source-agreements"; StatusMsg: "Installing Winamp via winget (UAC prompt expected)..."; Flags: shellexec waituntilterminated; Check: not WinampInstalled
Filename: "{app}\ytm-winamp.exe"; Parameters: "setup --skin-only"; StatusMsg: "Setting the Winamp theme..."; Flags: runhidden waituntilterminated
Filename: "{app}\ytm-winamp.exe"; Parameters: "era"; Description: "Start the era radio now"; Flags: postinstall shellexec skipifsilent unchecked

[Code]
function WinampInstalled: Boolean;
begin
  Result := FileExists('C:\Program Files (x86)\Winamp\winamp.exe')
         or FileExists('C:\Program Files\Winamp\winamp.exe');
end;
