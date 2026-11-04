; class-score 3.0 安装脚本（Inno Setup 6）
; 用法：用 Inno Setup 6 打开本文件 → Build → Compile，产物输出到本目录下的 dist\
;
; 相对路径：下面所有 Source / SetupIconFile / OutputDir 都相对本脚本所在目录
; （仓库根目录），不再依赖 E:\class-score-Portable_2.0 这类绝对路径。
;
; 数据安全：安装包不包含 data\、db\、output\，升级时不会覆盖已有的
; data\config.json 和 scores.db —— 程序文件与用户数据彻底分离。

#define MyAppName "class-score"
#define MyAppVersion "3.0"
#define MyAppFullName "班级积分管理系统"
#define MyAppPublisher "liang-rising-star"
#define MyAppURL "https://github.com/liang-rising-star/class-score"
#define MyAppExeName "run.exe"

[Setup]
; AppId 与 2.0 完全一致：老用户升级时原地覆盖程序文件，数据目录保持不变。
AppId={{3EA9B10A-BFFF-4037-A892-B0F60277FDEC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppFullName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName=D:\{#MyAppName}_{#MyAppVersion}
DefaultGroupName={#MyAppFullName}
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=class-score_{#MyAppVersion}_Setup
SetupIconFile=logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dynamic
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppFullName} {#MyAppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"
Name: "english"; MessagesFile: "compiler:Languages\English.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 启动器、图标、文档
Source: "{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "启动.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "readme.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "用户手册.docx"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
; 程序本体（含内嵌 python 运行时）
; 排除项务必保留：data/db/output 是用户数据，__pycache__ 是编译缓存，
; python\Doc 是 CPython 文档、embed 压缩包是重复的运行时源包，均无需分发。
Source: "class-score-system\*"; DestDir: "{app}\class-score-system"; Excludes: "data\*,db\*,output\*,__pycache__\*,*.pyc,python\Doc\*,python\python-3.14.2-embed-amd64.zip"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppFullName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppFullName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppFullName}"; Flags: nowait postinstall skipifsilent
