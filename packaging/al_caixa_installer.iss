; packaging/al_caixa_installer.iss
; Compilar com Inno Setup (ISCC.exe) DEPOIS de rodar o PyInstaller,
; a partir da pasta dist/ORVYN gerada por ele.
; Gera: AL-Caixa-Setup-<versao>.exe (sistema de mercado / PDV)

#define MyAppName "AL Caixa"
#define MyAppVersion GetFileVersion("..\dist\AL Caixa.exe")
#define MyAppPublisher "Aykon"
#define MyAppExeName "AL Caixa.exe"

[Setup]
AppId={{B1E1F5B0-COMERCIALPRO-4A1A-9C1E-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AL Caixa
DefaultGroupName=AL Caixa
DisableProgramGroupPage=yes
OutputDir=..\dist_installers
OutputBaseFilename=AL-Caixa-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\assets\icons\orvyn.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardImageFile=wizard\al_caixa_large.bmp
WizardSmallImageFile=wizard\al_caixa_small.bmp

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na área de trabalho"; GroupDescription: "Ícones adicionais:"

[Files]
Source: "..\dist\AL Caixa.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AL Caixa"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\AL Caixa"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir AL Caixa agora"; Flags: nowait postinstall skipifsilent
