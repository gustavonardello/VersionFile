; VersionFile — Script do Inno Setup
;
; Compilar com:
;   ISCC installer\VersionFile.iss /DAppVersion=1.2.2
;
; IMPORTANTE: Este instalador NUNCA encosta em {localappdata}\VersionFile,
; que é a pasta de DADOS do usuário (banco de regras, configs). A instalação
; vai para {localappdata}\Programs\VersionFile — caminho completamente
; separado. Conferir core/paths.py (data_path vs base_path) antes de
; qualquer alteração aqui.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName=VersionFile
AppVersion={#AppVersion}
AppPublisher=Gustavo Nardello
AppPublisherURL=https://github.com/gustavonardello/VersionFile
DefaultDirName={localappdata}\Programs\VersionFile
DefaultGroupName=VersionFile
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=VersionFile-{#AppVersion}-Setup
SetupIconFile=..\icone.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\VersionFile.exe
; Não perguntar sobre pasta de instalação — usuário sem admin não tem
; liberdade de escolher Program Files de qualquer forma
DisableDirPage=yes
; Usa o Restart Manager do Windows para fechar o VersionFile.exe antigo
; antes de sobrescrever os arquivos — elimina a condição de corrida entre
; self.close() do Python e a cópia do instalador.
; A reabertura fica por conta da entrada [Run], não do RestartApplications.
CloseApplications=yes
CloseApplicationsFilter=VersionFile.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; Copia todo o conteúdo de dist\VersionFile\ (saída do PyInstaller onedir)
Source: "..\dist\VersionFile\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VersionFile"; Filename: "{app}\VersionFile.exe"
Name: "{group}\Desinstalar VersionFile"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VersionFile"; Filename: "{app}\VersionFile.exe"; Tasks: icone_desktop

[Tasks]
Name: "icone_desktop"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"

[UninstallDelete]
; Remove subpastas vazias que createallsubdirs cria mas o Inno nao rastreia.
; Apenas a pasta de INSTALACAO ({app}) — NUNCA a pasta de dados do usuario.
Type: filesandordirs; Name: "{app}\_internal"

[Run]
Filename: "{app}\VersionFile.exe"; Description: "Iniciar o VersionFile"; Flags: nowait postinstall runasoriginaluser
