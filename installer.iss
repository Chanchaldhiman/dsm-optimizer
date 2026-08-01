; DSM Optimizer - Windows installer (Inno Setup, https://jrsoftware.org/isinfo.php)
;
; Why this exists: a zipped exe cannot give .dsmproj files their own icon or
; double-click-to-open behaviour - file associations live in the Windows
; registry, which only an installer can write. Build the app first
; (build_exe.bat), then compile this script with Inno Setup to get a
; setup.exe that installs the app, registers .dsmproj with the DSM icon,
; and adds Start-menu/desktop shortcuts.
;
; Compile: iscc installer.iss   (or open in the Inno Setup GUI)

#define AppName "DSM Optimizer"
#define AppVersion "3.4.5"
#define AppExe "DSM_Optimizer.exe"

[Setup]
AppId={{7B4E2C11-9C5A-4D1F-8E2B-DSMOPTIMIZER}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Chanchal Dhiman
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=DSM_Optimizer_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; file associations need this so Explorer refreshes icons after install
ChangesAssociations=yes

[Files]
; the whole onedir build output
Source: "dist\DSM_Optimizer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Registry]
; .dsmproj  ->  DSMOptimizer.Project  ->  icon + open command
Root: HKA; Subkey: "Software\Classes\.dsmproj"; ValueType: string; ValueName: ""; ValueData: "DSMOptimizer.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\DSMOptimizer.Project"; ValueType: string; ValueName: ""; ValueData: "DSM Optimizer Project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\DSMOptimizer.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\assets\icon.ico"
Root: HKA; Subkey: "Software\Classes\DSMOptimizer.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
