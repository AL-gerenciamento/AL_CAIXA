; packaging/superadmin_installer.iss
; Compilar com Inno Setup (ISCC.exe) DEPOIS de rodar o PyInstaller,
; a partir da pasta dist/ORVYN-Master gerada por ele.
; Gera: ALGL-mercado-Setup-<versao>.exe (painel do Super Admin)

#define MyAppName "ALGL mercado"
#define MyAppVersion GetFileVersion("..\dist\ALGL mercado.exe")
#define MyAppPublisher "Aykon"
#define MyAppExeName "ALGL mercado.exe"

[Setup]
AppId={{B1E1F5B0-ORVYNMASTER-4A1A-9C1E-000000000002}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ALGL mercado
DefaultGroupName=ALGL mercado
DisableProgramGroupPage=yes
OutputDir=..\dist_installers
OutputBaseFilename=ALGL-mercado-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\assets\icons\orvyn_master.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na área de trabalho"; GroupDescription: "Ícones adicionais:"

[Files]
Source: "..\dist\ALGL mercado.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ALGL mercado"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ALGL mercado"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir ALGL mercado agora"; Flags: nowait postinstall skipifsilent
