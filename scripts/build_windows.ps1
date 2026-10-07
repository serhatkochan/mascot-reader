[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$SkipModelDownload,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $Python) {
    $Python = Join-Path $projectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python not found: $Python. Create .venv with Python 3.11 and install .[dev] first."
}
$Python = (Resolve-Path -LiteralPath $Python).Path
$originalBuildPath = $env:PATH
$originalPythonPath = $env:PYTHONPATH
Push-Location -LiteralPath $projectRoot
try {
    $pythonBase = & $Python -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw "Python runtime detection failed." }
    $env:PATH = "$(Split-Path -Parent $Python);$pythonBase;$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONPATH = $null
    & $Python -c "import platform, struct, sys; assert sys.platform == 'win32' and struct.calcsize('P') == 8, 'Build requires 64-bit Windows'; assert sys.version_info[:2] == (3, 11), 'Build requires Python 3.11'; import torch; assert torch.version.cuda is None, 'Install the CPU PyTorch wheel before packaging'"
    if ($LASTEXITCODE -ne 0) { throw "Build environment validation failed." }
    $modelArguments = @((Join-Path $PSScriptRoot "fetch_model.py"))
    if ($SkipModelDownload) { $modelArguments += "--verify-only" }
    & $Python @modelArguments
    if ($LASTEXITCODE -ne 0) { throw "Model cache preparation failed." }
    $buildArguments = @("-m", "PyInstaller", "--noconfirm", "--log-level", "WARN")
    if ($Clean) { $buildArguments += "--clean" }
    $buildArguments += (Join-Path $projectRoot "MascotReader.spec")
    & $Python @buildArguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    $distribution = Join-Path $projectRoot "dist\MascotReader"
    $archive = Join-Path $projectRoot "dist\MascotReader-windows-x64.zip"
    $mascotDirectory = Join-Path $distribution "_internal\resources\mascots"
    $mascotCatalog = Get-Content -LiteralPath (Join-Path $mascotDirectory "catalog.json") -Raw | ConvertFrom-Json
    if (@($mascotCatalog.mascots).Count -ne 10) { throw "The frozen mascot catalog must contain ten choices." }
    foreach ($mascot in $mascotCatalog.mascots) {
        $metadataPath = Join-Path $mascotDirectory $mascot.metadata
        $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
        if (-not (Test-Path -LiteralPath (Join-Path $mascotDirectory $metadata.image) -PathType Leaf)) {
            throw "Missing frozen mascot sprite: $($mascot.id)"
        }
    }
    $verification = Join-Path $projectRoot "build\verification"
    New-Item -ItemType Directory -Path $verification -Force | Out-Null
    $smokeOutput = Join-Path $verification ("frozen-smoke-" + [guid]::NewGuid().ToString("N") + ".wav")
    $previousLocalAppData = $env:LOCALAPPDATA
    $previousPath = $env:PATH
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousQtBackend = $env:QT_MEDIA_BACKEND
    try {
        $env:LOCALAPPDATA = Join-Path $verification "profile"
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        $smokeProcess = Start-Process -FilePath (Join-Path $distribution "MascotReader.exe") -ArgumentList @("--smoke-test", ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
        if (-not $smokeProcess.WaitForExit(60000)) {
            $smokeProcess.Kill()
            throw "Frozen offline synthesis verification timed out."
        }
        $smokeProcess.Refresh()
        if ($smokeProcess.ExitCode -ne 0) { throw "Frozen offline synthesis verification failed." }
        $smokeResult = Get-Content -LiteralPath ([IO.Path]::ChangeExtension($smokeOutput, ".json")) -Raw | ConvertFrom-Json
        if (-not $smokeResult.frozen -or -not $smokeResult.offline -or $smokeResult.sample_rate -ne 48000 -or $smokeResult.channels -ne 1 -or $smokeResult.sample_width -ne 2 -or $smokeResult.frames -le 0) {
            throw "Frozen verification returned invalid WAV metadata."
        }
        $cueReport = [IO.Path]::ChangeExtension($smokeOutput, ".cues.json")
        $cueResult = Get-Content -LiteralPath $cueReport -Raw | ConvertFrom-Json
        if ($cueResult.schema_version -ne 1 -or $cueResult.sample_rate -ne $smokeResult.sample_rate -or $cueResult.source_text -isnot [string] -or $cueResult.cues -isnot [array] -or $cueResult.cues.Count -eq 0) {
            throw "Frozen verification returned invalid or empty reading cues."
        }
        $cueEndFrame = 0
        foreach ($cue in $cueResult.cues) {
            $validStart = $cue.start_frame -is [int] -or $cue.start_frame -is [long]
            $validEnd = $cue.end_frame -is [int] -or $cue.end_frame -is [long]
            if (-not $validStart -or -not $validEnd -or $cue.start_frame -ne $cueEndFrame -or $cue.end_frame -lt $cue.start_frame -or $cue.end_frame -gt $smokeResult.frames) {
                throw "Frozen reading cue boundaries do not match the WAV frames."
            }
            $cueEndFrame = $cue.end_frame
        }
        if ($cueEndFrame -ne $smokeResult.frames) { throw "Frozen reading cues do not cover the whole WAV." }
        Copy-Item -LiteralPath $smokeOutput -Destination (Join-Path $verification "frozen-smoke.wav") -Force
        Copy-Item -LiteralPath ([IO.Path]::ChangeExtension($smokeOutput, ".json")) -Destination (Join-Path $verification "frozen-smoke.json") -Force
        Copy-Item -LiteralPath $cueReport -Destination (Join-Path $verification "frozen-smoke.cues.json") -Force
        Write-Host "Verified offline CPU synthesis from the frozen application."
        Write-Host "Verified frame-derived reading cues against the complete WAV."
        $env:QT_QPA_PLATFORM = "windows"
        $env:QT_MEDIA_BACKEND = "ffmpeg"
        $playbackProcess = Start-Process -FilePath (Join-Path $distribution "MascotReader.exe") -ArgumentList @("--verify-playback", ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
        if (-not $playbackProcess.WaitForExit(15000)) {
            $playbackProcess.Kill()
            throw "Frozen Qt playback verification timed out."
        }
        $playbackProcess.Refresh()
        if ($playbackProcess.ExitCode -ne 0) { throw "Frozen Qt playback verification failed." }
        $playbackReport = [IO.Path]::ChangeExtension($smokeOutput, ".playback.json")
        $playbackResult = Get-Content -LiteralPath $playbackReport -Raw | ConvertFrom-Json
        if (-not $playbackResult.frozen -or -not $playbackResult.seekable -or -not $playbackResult.restart -or $playbackResult.stopped_at_ms -ne 0 -or $playbackResult.duration_ms -le 0) {
            throw "Frozen Qt playback verification returned invalid transport metadata."
        }
        $targetCue = $cueResult.cues[[Math]::Min(1, $cueResult.cues.Count - 1)]
        $expectedSegmentMs = [long][Math]::Ceiling($targetCue.start_frame * 1000.0 / $cueResult.sample_rate)
        $validSegmentPosition = $playbackResult.segment_seek_ms -is [int] -or $playbackResult.segment_seek_ms -is [long]
        if ($playbackResult.mascots -ne 10 -or $playbackResult.cue_count -ne $cueResult.cues.Count -or $playbackResult.linked_cues -ne $playbackResult.cue_count -or -not $playbackResult.segment_seek -or -not $validSegmentPosition -or $playbackResult.segment_seek_ms -ne $expectedSegmentMs) {
            throw "Frozen mascot gallery or measured reading-segment seeking verification failed."
        }
        Copy-Item -LiteralPath $playbackReport -Destination (Join-Path $verification "frozen-smoke.playback.json") -Force
        Write-Host "Verified frozen Qt WAV decoding, seeking, restart, and stop."
        Write-Host "Verified ten frozen mascots and linked frame-derived reading segments."
    }
    finally {
        $env:LOCALAPPDATA = $previousLocalAppData
        $env:PATH = $previousPath
        $env:QT_QPA_PLATFORM = $previousQtPlatform
        $env:QT_MEDIA_BACKEND = $previousQtBackend
    }
    & $Python (Join-Path $PSScriptRoot "package_windows.py")
    if ($LASTEXITCODE -ne 0) { throw "Release documentation or ZIP creation failed." }
    Write-Host "Portable application: $distribution\MascotReader.exe"
    Write-Host "Portable ZIP: $archive"
}
finally {
    $env:PATH = $originalBuildPath
    $env:PYTHONPATH = $originalPythonPath
    Pop-Location
}
