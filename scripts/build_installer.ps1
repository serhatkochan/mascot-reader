[CmdletBinding()]
param(
    [string]$Iscc = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$scriptPath = Join-Path $projectRoot "installer\mascot-reader.iss"
$distribution = Join-Path $projectRoot "dist\MascotReader"
$applicationExe = Join-Path $distribution "MascotReader.exe"
if (-not (Test-Path -LiteralPath $applicationExe -PathType Leaf)) {
    throw "Build dist\MascotReader with scripts\build_windows.ps1 before creating the installer."
}
if (-not $Python) { $Python = Join-Path $projectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python not found: $Python" }
$Python = (Resolve-Path -LiteralPath $Python).Path
if (-not $Iscc) {
    $compilerCandidates = @(
        (Join-Path $projectRoot ".tools\inno\compiler\ISCC.exe"),
        (Join-Path $projectRoot ".tools\inno\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $Iscc = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Iscc) {
        $compilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($compilerCommand) { $Iscc = $compilerCommand.Source }
    }
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc -PathType Leaf)) {
    throw "Inno Setup 6 compiler not found. Supply -Iscc <path to ISCC.exe>."
}
$Iscc = (Resolve-Path -LiteralPath $Iscc).Path
$versionCode = @'
import ast, json, pathlib, sys, tomllib
root = pathlib.Path(sys.argv[1])
project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
tree = ast.parse((root / 'src/mascot_reader/__init__.py').read_text(encoding='utf-8'))
package = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets))
assert project == package, 'pyproject.toml and package __version__ disagree'
print(json.dumps({'version': project}))
'@
$sourceVersionJson = & $Python -c $versionCode $projectRoot
if ($LASTEXITCODE -ne 0) { throw "Source version validation failed." }
$version = ($sourceVersionJson | ConvertFrom-Json).version
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "Installer requires a numeric major.minor.patch version." }
$identity = [regex]::Match((Get-Content -LiteralPath $scriptPath -Raw), '#define AppIdentity "([A-Fa-f0-9-]{36})"').Groups[1].Value
if (-not $identity) { throw "The installer script has no stable AppIdentity UUID." }
$runDirectory = Join-Path $projectRoot ("build\installer\" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
$versionReport = Join-Path $runDirectory "application-version.json"
$previousPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $versionProcess = Start-Process -FilePath $applicationExe -ArgumentList @("--version-file", ('"' + $versionReport + '"')) -WindowStyle Hidden -PassThru
    $versionProcess.Handle | Out-Null
    if (-not $versionProcess.WaitForExit(15000)) {
        $versionProcess.Kill()
        throw "The frozen application version check timed out. Rebuild the Windows distribution."
    }
    $versionProcess.Refresh()
    if ($versionProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $versionReport -PathType Leaf)) {
        throw "The frozen application cannot report its version. Rebuild the Windows distribution."
    }
    $binaryVersion = Get-Content -LiteralPath $versionReport -Raw | ConvertFrom-Json
    if (-not $binaryVersion.frozen -or $binaryVersion.version -ne $version) {
        throw "Frozen application version does not match source $version. Rebuild the Windows distribution."
    }
}
finally { $env:PATH = $previousPath }

$manifest = Join-Path $runDirectory "application-files.sha256"
$manifestLines = [Collections.Generic.List[string]]::new()
$manifestLines.Add("MascotReader-managed-files-v1:$identity")
$distributionPrefix = [IO.Path]::GetFullPath($distribution).TrimEnd('\') + '\'
$payloadEntries = @(Get-ChildItem -LiteralPath $distribution -Force -Recurse)
foreach ($entry in $payloadEntries) {
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Payload contains a reparse point: $($entry.FullName)" }
}
$payloadFiles = @($payloadEntries | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName)
foreach ($file in $payloadFiles) {
    if (-not $file.FullName.StartsWith($distributionPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unexpected file outside the distribution: $($file.FullName)"
    }
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Payload contains a reparse point: $($file.FullName)" }
    $relative = $file.FullName.Substring($distributionPrefix.Length)
    if ($relative -match '[|\r\n]') { throw "Unsupported payload filename: $relative" }
    $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestLines.Add("$fileHash|$relative")
}
[IO.File]::WriteAllLines($manifest, $manifestLines, [Text.UTF8Encoding]::new($true))
$applicationHash = (Get-FileHash -LiteralPath $applicationExe -Algorithm SHA256).Hash.ToLowerInvariant()
$compileDirectory = Join-Path $runDirectory "output"
$compileArguments = @("/Qp", "/DAppVersion=$version", "/DPayloadDir=$distribution", "/DFileManifest=$manifest", "/DInstallerOutputDir=$compileDirectory", $scriptPath)
& $Iscc @compileArguments
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
$compiledInstaller = [IO.Path]::GetFullPath((Join-Path $compileDirectory "MascotReader-Setup.exe"))
$runPrefix = [IO.Path]::GetFullPath($runDirectory).TrimEnd('\') + '\'
if (-not $compiledInstaller.StartsWith($runPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Compiler output escaped its build directory." }
if (-not (Test-Path -LiteralPath $compiledInstaller -PathType Leaf)) { throw "Inno Setup did not produce the expected installer." }
if ((Get-FileHash -LiteralPath $applicationExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $applicationHash) { throw "Application EXE changed while creating the installer." }
$installer = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist\MascotReader-Setup.exe"))
$distPrefix = [IO.Path]::GetFullPath((Join-Path $projectRoot "dist")).TrimEnd('\') + '\'
if (-not $installer.StartsWith($distPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Installer target escaped dist." }
Move-Item -LiteralPath $compiledInstaller -Destination $installer -Force
$installerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($installer + ".sha256", "$installerHash  MascotReader-Setup.exe`n", [Text.Encoding]::ASCII)
$summary = [ordered]@{
    version = $version
    installer = $installer
    bytes = (Get-Item -LiteralPath $installer).Length
    sha256 = $installerHash
    application_exe_sha256 = $applicationHash
    app_id = $identity
    compiler = $Iscc
    manifest_files = $payloadFiles.Count
}
$summaryJson = $summary | ConvertTo-Json
$reportDirectory = Join-Path $projectRoot "build\verification"
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $reportDirectory "installer-summary.json"), $summaryJson, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $projectRoot "dist\MascotReader-Setup.build.json"), $summaryJson, [Text.UTF8Encoding]::new($false))
Write-Output $summaryJson
