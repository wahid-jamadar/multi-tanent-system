#define MyAppName "FileBridge Agent"
#define MyAppVersion "1.5.0"
#define MyAppExeName "FileBridgeAgent.exe"

[Setup]
AppId={{6D7D3D66-DB40-4B1E-A24A-FILEBRIDGE15}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\FileBridgeAgent
DefaultGroupName=FileBridge
DisableProgramGroupPage=yes
OutputBaseFilename=FileBridgeAgentSetup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Files]
Source: "dist\FileBridgeAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.yaml"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "install_service.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_service.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Install FileBridge Agent Service"; Filename: "{app}\install_service.bat"
Name: "{group}\Uninstall FileBridge Agent Service"; Filename: "{app}\uninstall_service.bat"

[Run]
Filename: "{app}\install_service.bat"; Description: "Install and start FileBridge Agent service"; Flags: runhidden

[UninstallRun]
Filename: "{app}\uninstall_service.bat"; Flags: runhidden
