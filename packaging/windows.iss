#ifndef AppVersion
#define AppVersion "0.4.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\LinguaCaption"
#endif
#ifndef PackageDir
  #define PackageDir "..\dist"
#endif

[Setup]
AppId={{DF5CA629-54B1-486F-AF0C-B68CF014E549}
AppName=LinguaCaption
AppVersion={#AppVersion}
AppPublisher=LinguaCaption contributors
AppPublisherURL=https://github.com/zhangmingfeng962-cyber/LinguaCaption
AppSupportURL=https://github.com/zhangmingfeng962-cyber/LinguaCaption/issues
DefaultDirName={localappdata}\Programs\LinguaCaption
DefaultGroupName=LinguaCaption
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#PackageDir}
OutputBaseFilename=LinguaCaption-{#AppVersion}-windows-x64-setup
SetupIconFile=..\src\linguacaption\assets\app.ico
UninstallDisplayIcon={app}\LinguaCaption.exe
Compression=lzma2/fast
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2
WizardStyle=modern
LicenseFile=..\LICENSE
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LinguaCaption"; Filename: "{app}\LinguaCaption.exe"
Name: "{autodesktop}\LinguaCaption"; Filename: "{app}\LinguaCaption.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LinguaCaption.exe"; Description: "Launch LinguaCaption"; Flags: nowait postinstall skipifsilent
