param(
    [switch]$SkipInstall,
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$DistApp = Join-Path $Root "dist\seshat-tts"
$DistExe = Join-Path $Root "dist\seshat-tts.exe"

$RunningApps = @(Get-Process -Name "seshat-tts" -ErrorAction SilentlyContinue)
foreach ($Process in $RunningApps) {
    try {
        Stop-Process -Id $Process.Id -Force -ErrorAction Stop
    } catch {
        & taskkill.exe /PID $Process.Id /T /F | Out-Null
    }
}
Start-Sleep -Milliseconds 500
$StillRunning = @(Get-Process -Name "seshat-tts" -ErrorAction SilentlyContinue)
if ($StillRunning.Count -gt 0) {
    $Ids = ($StillRunning | ForEach-Object { $_.Id }) -join ", "
    throw "Close Seshat TTS before building. Could not stop running process id(s): $Ids"
}
foreach ($Target in @($DistApp, $DistExe)) {
    if (Test-Path $Target) {
        for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
            try {
                Remove-Item -LiteralPath $Target -Recurse -Force
                break
            } catch {
                if ($Attempt -eq 5) {
                    throw
                }
                Start-Sleep -Seconds 2
            }
        }
    }
}

if (-not $SkipInstall) {
    python -m pip install --upgrade pip
    python -m pip install -e ".[build,test]"
}

if ($OneDir) {
    python -m PyInstaller --clean --noconfirm seshat-tts.spec
    Write-Host "Built: $Root\dist\seshat-tts\seshat-tts.exe"
} else {
    python -m PyInstaller --clean --noconfirm seshat-tts-portable.spec
    Write-Host "Built portable EXE: $Root\dist\seshat-tts.exe"
}

Write-Host "The portable EXE bundles the GUI runtime, bundled OCR files when Tesseract is installed on this build machine, and uvx.exe when found."
