; Inno Setup Script for ChronoRecovery
; Generates ChronoRecovery-Setup.exe installer wizard

#define MyAppName "ChronoRecovery"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Jose Manuel TG"
#define MyAppExeName "ChronoRecovery.exe"
#define MyAppCliName "chrono.exe"

[Setup]
; App Identity
AppId={{D8F91A2B-3C4D-4E5F-6A7B-8C9D0E1F2A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=ChronoRecovery-Setup-{#MyAppVersion}
SetupIconFile=assets\icons\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Require admin so raw drive / physical sector recovery works out of the box
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; File association for .rsf
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate_rsf"; Description: "Associate .rsf files (ChronoRecovery Scan Sessions) with ChronoRecovery"; GroupDescription: "File Associations:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyAppCliName}"; DestDir: "{app}"; Flags: ignoreversion; Tasks: 
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\app_icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icons\app_icon.ico"; Tasks: desktopicon

[Registry]
; Register .rsf file extension
Root: HKA; Subkey: "Software\Classes\.rsf"; ValueType: string; ValueName: ""; ValueData: "ChronoRecovery.RSF"; Flags: uninsdeletevalue; Tasks: associate_rsf
Root: HKA; Subkey: "Software\Classes\.rsf"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-chronorecovery-session"; Flags: uninsdeletevalue; Tasks: associate_rsf
Root: HKA; Subkey: "Software\Classes\ChronoRecovery.RSF"; ValueType: string; ValueName: ""; ValueData: "ChronoRecovery Scan Session"; Flags: uninsdeletekey; Tasks: associate_rsf
Root: HKA; Subkey: "Software\Classes\ChronoRecovery.RSF\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\assets\icons\app_icon.ico,0"; Flags: uninsdeletekey; Tasks: associate_rsf
Root: HKA; Subkey: "Software\Classes\ChronoRecovery.RSF\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: associate_rsf

; Add application folder to PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
