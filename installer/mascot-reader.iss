#ifndef AppVersion
  #error Pass AppVersion from scripts/build_installer.ps1
#endif
#ifndef PayloadDir
  #error Pass PayloadDir from scripts/build_installer.ps1
#endif
#ifndef FileManifest
  #error Pass FileManifest from scripts/build_installer.ps1
#endif
#ifndef InstallerOutputDir
  #error Pass InstallerOutputDir from scripts/build_installer.ps1
#endif
#ifndef AppIdentity
  #define AppIdentity "8EE59C11-1BF6-43AD-979E-6817074062A8"
#endif
#ifndef AppName
  #define AppName "MascotReader"
#endif
#define AppExe "MascotReader.exe"
#define ProjectURL "https://github.com/serhatkochan/markdown-to-speech"

[Setup]
AppId={{{#AppIdentity}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=serhatkochan
AppPublisherURL={#ProjectURL}
AppSupportURL={#ProjectURL}/issues
AppUpdatesURL={#ProjectURL}/releases/latest
AppReadmeFile={app}\README.md
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
AllowRootDirectory=no
AllowUNCPath=no
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallLogMode=append
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir={#InstallerOutputDir}
OutputBaseFilename=MascotReader-Setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourcePath}\..\resources\mascot.ico
SetupLogging=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription=MascotReader Windows kurulumu

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstünde kısayol oluştur"; GroupDescription: "Kısayollar:"

[Files]
Source: "{#FileManifest}"; DestName: "mascot-files.new"; Flags: dontcopy
Source: "{#FileManifest}"; DestDir: "{app}"; DestName: ".mascot-reader-files.sha256"; Attribs: hidden; Flags: ignoreversion; BeforeInstall: CaptureObsoleteManagedFiles
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "MascotReader'ı aç"; Flags: nowait postinstall skipifsilent

[Code]
const
  ManifestHeader = 'MascotReader-managed-files-v1:{#AppIdentity}';
  InvalidAttributes = $FFFFFFFF;
  ReparsePointAttribute = $400;

var
  CandidatesCaptured: Boolean;
  ObsoleteNames, ObsoleteDigests: TArrayOfString;

function GetFileAttributesW(const Filename: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function OpenApplicationFile(const Filename: String; DesiredAccess, ShareMode,
  SecurityAttributes, CreationDisposition, FlagsAndAttributes, TemplateFile: LongWord): LongWord;
  external 'CreateFileW@kernel32.dll stdcall';

function FinalApplicationPath(FileHandle: LongWord; Filename: String;
  BufferSize, Flags: LongWord): LongWord;
  external 'GetFinalPathNameByHandleW@kernel32.dll stdcall';

function CloseApplicationFile(FileHandle: LongWord): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function DedicatedAppDirectory: Boolean;
begin
  Result := CompareText(ExtractFileName(RemoveBackslash(ExpandConstant('{app}'))),
    '{#AppName}') = 0;
end;

function PathUsesReparsePoint(const Filename: String): Boolean;
var
  CurrentPath, ParentPath: String;
  Attributes: LongWord;
begin
  Result := False;
  CurrentPath := Filename;
  while CurrentPath <> '' do begin
    Attributes := GetFileAttributesW(CurrentPath);
    if (Attributes <> InvalidAttributes) and
       ((Attributes and ReparsePointAttribute) <> 0) then begin
      Result := True;
      Exit;
    end;
    ParentPath := ExtractFileDir(CurrentPath);
    if CompareText(ParentPath, CurrentPath) = 0 then Exit;
    CurrentPath := ParentPath;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not DedicatedAppDirectory then
    Result := 'Kurulum klasörünün adı MascotReader olmalıdır.'
  else if PathUsesReparsePoint(ExpandConstant('{app}')) then
    Result := 'Kurulum klasörü sembolik bağlantı veya junction içermemelidir.';
end;

function ParseManifestLine(const Line: String; var RelativeName, Digest: String): Boolean;
var
  Separator, Index: Integer;
begin
  Result := False;
  Separator := Pos('|', Line);
  if Separator <> 65 then Exit;
  Digest := Lowercase(Copy(Line, 1, 64));
  for Index := 1 to 64 do
    if Pos(Digest[Index], '0123456789abcdef') = 0 then Exit;
  RelativeName := Copy(Line, Separator + 1, Length(Line));
  StringChangeEx(RelativeName, '/', '\', True);
  if RelativeName = '' then Exit;
  if (RelativeName[1] = '\') or (Pos(':', RelativeName) <> 0) or
     (Pos('..', RelativeName) <> 0) or (Pos('|', RelativeName) <> 0) then Exit;
  Result := True;
end;

function ManagedCleanupPath(const RelativeName: String): String;
var
  LowerName, AppPrefix, Target: String;
begin
  Result := '';
  LowerName := Lowercase(RelativeName);
  if (Pos('_internal\', LowerName) <> 1) and
     (Pos('docs\assets\', LowerName) <> 1) then Exit;
  if not DedicatedAppDirectory then Exit;
  AppPrefix := AddBackslash(ExpandFileName(ExpandConstant('{app}')));
  Target := ExpandFileName(AppPrefix + RelativeName);
  if Pos(Lowercase(AppPrefix), Lowercase(Target)) <> 1 then Exit;
  if PathUsesReparsePoint(Target) then Exit;
  Result := Target;
end;

procedure CaptureObsoleteManagedFiles;
var
  OldLines, NewLines: TArrayOfString;
  CurrentNames: TStringList;
  Index, CandidateCount: Integer;
  OldManifest, RelativeName, Digest: String;
begin
  if CandidatesCaptured then Exit;
  CandidatesCaptured := True;
  OldManifest := ExpandConstant('{app}\.mascot-reader-files.sha256');
  if not FileExists(OldManifest) then Exit;
  if PathUsesReparsePoint(OldManifest) then Exit;
  if not LoadStringsFromFile(OldManifest, OldLines) then Exit;
  if GetArrayLength(OldLines) = 0 then Exit;
  if OldLines[0] <> ManifestHeader then Exit;
  ExtractTemporaryFile('mascot-files.new');
  if not LoadStringsFromFile(ExpandConstant('{tmp}\mascot-files.new'), NewLines) then
    RaiseException('Yeni kurulum dosya listesi okunamadı.');
  if GetArrayLength(NewLines) = 0 then
    RaiseException('Yeni kurulum dosya listesi boş.');
  if NewLines[0] <> ManifestHeader then
    RaiseException('Yeni kurulum dosya listesi geçersiz.');
  CurrentNames := TStringList.Create;
  try
    CurrentNames.CaseSensitive := False;
    CurrentNames.Sorted := True;
    CurrentNames.Duplicates := dupIgnore;
    for Index := 1 to GetArrayLength(NewLines) - 1 do
      if ParseManifestLine(NewLines[Index], RelativeName, Digest) then
        CurrentNames.Add(RelativeName);
    for Index := 1 to GetArrayLength(OldLines) - 1 do begin
      if not ParseManifestLine(OldLines[Index], RelativeName, Digest) then Continue;
      if CurrentNames.IndexOf(RelativeName) >= 0 then Continue;
      if ManagedCleanupPath(RelativeName) = '' then Continue;
      CandidateCount := GetArrayLength(ObsoleteNames);
      SetArrayLength(ObsoleteNames, CandidateCount + 1);
      SetArrayLength(ObsoleteDigests, CandidateCount + 1);
      ObsoleteNames[CandidateCount] := RelativeName;
      ObsoleteDigests[CandidateCount] := Digest;
    end;
  finally
    CurrentNames.Free;
  end;
end;

procedure RemoveObsoleteManagedFiles;
var
  Index: Integer;
  RelativeName, Target: String;
begin
  for Index := 0 to GetArrayLength(ObsoleteNames) - 1 do begin
    RelativeName := ObsoleteNames[Index];
    Target := ManagedCleanupPath(RelativeName);
    if Target = '' then Continue;
    if not FileExists(Target) then Continue;
    try
      if CompareText(GetSHA256OfFile(Target), ObsoleteDigests[Index]) <> 0 then begin
        Log('Changed file preserved: ' + RelativeName);
        Continue;
      end;
      if DeleteFile(Target) then
        Log('Obsolete installer-owned file removed: ' + RelativeName)
      else
        Log('Obsolete installer-owned file could not be removed: ' + RelativeName);
    except
      Log('Obsolete installer-owned file check failed: ' + RelativeName);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then RemoveObsoleteManagedFiles;
end;

function AsciiApplicationPath(const Filename: String): String;
var
  Index: Integer;
begin
  Result := ExpandFileName(Filename);
  StringChangeEx(Result, '/', '\', True);
  for Index := 1 to Length(Result) do
    if (Result[Index] >= 'A') and (Result[Index] <= 'Z') then
      Result[Index] := Chr(Ord(Result[Index]) + 32);
end;

function CanonicalApplicationPath(const Filename: String): String;
var
  FileHandle, PathLength: LongWord;
  Buffer: String;
begin
  Result := '';
  FileHandle := OpenApplicationFile(Filename, 0, 7, 0, 3, 0, 0);
  if FileHandle = InvalidAttributes then Exit;
  try
    SetLength(Buffer, 32768);
    PathLength := FinalApplicationPath(FileHandle, Buffer, Length(Buffer), 0);
    if (PathLength = 0) or (PathLength >= LongWord(Length(Buffer))) then Exit;
    SetLength(Buffer, PathLength);
    if Copy(Buffer, 1, 8) = '\\?\UNC\' then
      Buffer := '\\' + Copy(Buffer, 9, Length(Buffer))
    else if Copy(Buffer, 1, 4) = '\\?\' then
      Delete(Buffer, 1, 4);
    Result := AsciiApplicationPath(Buffer);
  finally
    CloseApplicationFile(FileHandle);
  end;
end;

function InitializeUninstall: Boolean;
var
  ApplicationFile, ApplicationPath, MutexName: String;
begin
  Result := False;
  ApplicationFile := ExpandConstant('{app}\{#AppExe}');
  ApplicationPath := CanonicalApplicationPath(ApplicationFile);
  if ApplicationPath = '' then begin
    if not FileExists(ApplicationFile) then begin
      Result := True;
      Exit;
    end;
    Log('Uninstall blocked: the application path could not be resolved.');
    if not UninstallSilent then
      SuppressibleMsgBox('Uygulama dosyasının konumu doğrulanamadı. Kaldırma başlatılmadı.',
        mbError, MB_OK, IDOK);
    Exit;
  end;
  MutexName := 'Local\MascotReader-' + Lowercase(GetSHA256OfUnicodeString(ApplicationPath));
  while CheckForMutexes(MutexName) do begin
    Log('Uninstall blocked: the installed MascotReader application is running.');
    if UninstallSilent then Exit;
    if SuppressibleMsgBox(
      'MascotReader çalışıyor. Maskota veya sistem tepsisi simgesine sağ tıklayıp ' +
      'Çıkış seçeneğini kullanın. Ardından devam etmek için Tamam''a basın.',
      mbInformation, MB_OKCANCEL, IDCANCEL) <> IDOK then Exit;
  end;
  Result := True;
end;
