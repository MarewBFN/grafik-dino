; Instalator dla kanału Enyo (klient: ochrona) - osobny plik od
; "dla inno.iss" (Dingo/kanał główny), żeby branding i AppId nigdy się nie
; pomyliły między kanałami. Wymaga wcześniejszego zbudowania
; "Enyo - Grafik Pracy.spec" przez PyInstaller (patrz
; scripts\build_release.ps1 -Channel enyo -SpecFile "Enyo - Grafik Pracy.spec").
; Non-commercial use only

#define MyAppName "Enyo - Grafik Pracy"
#define MyAppVersion "1.0.0.enyo"
#define MyAppPublisher "Kewin Madej"
#define MyAppURL "https://www.madebykewin.pl"
#define MyAppExeName "Enyo - Grafik Pracy.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".myp"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
; AppId CELOWO inny niż w "dla inno.iss" (Dingo) - to osobny produkt z
; perspektywy Windows (rejestr/odinstalowywanie), nie wariant tej samej
; instalacji, mimo wspólnego kodu źródłowego.
AppId={{8C714D0B-17B2-4F06-8813-0CACEADBD73D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\Enyo\Grafik Pracy
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=yes
; Instalator pisze do {localappdata} (per-user), ale przy PrivilegesRequired=admin
; elevacja moze zajsc na innym koncie administratora niz zalogowany uzytkownik -
; wtedy {localappdata} wskazuje na profil TEGO admina, a nie uzytkownika programu,
; wiec aktualizacja instaluje sie w innym miejscu i skrot dalej wskazuje na stara wersje.
PrivilegesRequired=lowest
OutputBaseFilename=EnyoSetup
OutputDir=Output
SetupIconFile=C:\Users\kewi1\Desktop\madebykewin\Grafik dino V2\dingo_icon.ico
SolidCompression=yes
WizardStyle=modern dynamic

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "C:\Users\kewi1\Desktop\madebykewin\Grafik dino V2\dist\Enyo - Grafik Pracy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Znaczniki "widziano samouczek" (np. CONFIG_TUTORIAL_FLAG w
; ui/config_dialog.py, LOCATIONS_TUTORIAL_FLAG itd.) - aplikacja tworzy je
; przy pierwszym uruchomieniu w SWOIM WŁASNYM katalogu roboczym ({app}, bo
; skróty w [Icons] nie ustawiają WorkingDir - patrz też "last_project.json").
; Domyślny deinstalator kasuje tylko pliki wpisane w [Files], więc bez tego
; te znaczniki zostałyby osierocone po odinstalowaniu - przy ponownej
; instalacji samouczki "pamiętałyby" (błędnie), że użytkownik już je widział.
Type: files; Name: "{app}\*.flag"
