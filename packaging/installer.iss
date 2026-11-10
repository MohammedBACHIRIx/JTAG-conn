; Inno Setup script for JTAG-conn
; Builds JTAG-conn-Setup.exe from dist\JTAG-conn.exe

#define MyAppName "JTAG-conn"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "JTAG-conn"
#define MyAppExeName "JTAG-conn.exe"

[Setup]
AppId={{A9D4B6E2-8C4A-4E5D-9F31-7B2C1D0E4F55}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=JTAG-conn-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\JTAG-conn.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Associate .jtagc.json session files with JTAG-conn
Root: HKCU; Subkey: "Software\Classes\.jtagc.json"; ValueType: string; ValueName: ""; ValueData: "JTAGConn.Session"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\JTAGConn.Session"; ValueType: string; ValueName: ""; ValueData: "JTAG-conn Session"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\JTAGConn.Session\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\JTAGConn.Session\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
