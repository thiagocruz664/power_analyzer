#define MyAppName "Power Analyzer"
#define MyAppVersion "0.1.0-beta"
#define MyAppExeName "PowerAnalyzer.exe"

[Setup]
AppId={{A73E4C31-8F52-4A91-BD6E-2F7C5A9D1042}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Power Analyzer
DefaultDirName={autopf}\PowerAnalyzer
DefaultGroupName=Power Analyzer
OutputDir=dist_installer
OutputBaseFilename=PowerAnalyzer-beta-0.1.0-windows-x64
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\PowerAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Power Analyzer"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Power Analyzer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Power Analyzer"; Flags: postinstall nowait skipifsilent
