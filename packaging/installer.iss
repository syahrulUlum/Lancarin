; Inno Setup — bungkus hasil PyInstaller menjadi Lancarin-Setup.exe
[Setup]
AppName=Lancarin
AppVersion=0.1.0
DefaultDirName={autopf}\Lancarin
DefaultGroupName=Lancarin
OutputBaseFilename=Lancarin-Setup
SetupIconFile=..\assets\lancarin.ico
Compression=lzma2
SolidCompression=yes

[Files]
Source: "..\dist\Lancarin\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Lancarin"; Filename: "{app}\Lancarin.exe"; IconFilename: "{app}\Lancarin.exe"; IconIndex: 0
Name: "{autodesktop}\Lancarin"; Filename: "{app}\Lancarin.exe"; IconFilename: "{app}\Lancarin.exe"; IconIndex: 0

[Run]
Filename: "{app}\Lancarin.exe"; Description: "Jalankan Lancarin"; Flags: nowait postinstall skipifsilent
