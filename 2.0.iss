; 脚本由 Inno Setup 脚本向导生成。
; 有关创建 Inno Setup 脚本文件的详细信息，请参阅帮助文档！
; 仅供非商业使用

#define MyAppName "class-score_v2.0"
#define MyAppVersion "2.0"
#define MyAppPublisher "liang-rising-star"
#define MyAppURL "https://github.com/liang-rising-star/class-score"
#define MyAppExeName "run.exe"

[Setup]
; 注意：AppId 的值唯一标识此应用程序。不要在其他应用程序的安装程序中使用相同的 AppId 值。
; (若要生成新的 GUID，请在 IDE 中单击 "工具|生成 GUID"。)
AppId={{3EA9B10A-BFFF-4037-A892-B0F60277FDEC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName=D:/{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
LicenseFile=E:\class-score-Portable_2.0\readme.txt
InfoBeforeFile=E:\class-score-Portable_2.0\readme.txt
InfoAfterFile=E:\class-score-Portable_2.0\readme.txt
; 取消注释以下行以在非管理安装模式下运行 (仅为当前用户安装)。
;PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=E:\
OutputBaseFilename=class-score_v2.0_Setup
SetupIconFile=E:\class-score-Portable_2.0\logo.ico
SolidCompression=yes
WizardStyle=modern dynamic

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"
Name: "english"; MessagesFile: "compiler:Languages\English.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "E:\class-score-Portable_2.0\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "E:\class-score-Portable_2.0\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 注意：不要在任何共享系统文件上使用 "Flags: ignoreversion" 

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

