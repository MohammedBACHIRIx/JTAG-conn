Param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

Write-Host "==> Installing dependencies (including pyinstaller)"
python -m pip install --upgrade pip
if (Test-Path "pyproject.toml") {
    python -m pip install -e ".[dev]" pyinstaller
} else {
    python -m pip install pyinstaller
}

if (-not $SkipTests) {
    Write-Host "==> Running tests"
    python -m pytest -q
}

Write-Host "==> Building single-file JTAG-conn.exe with PyInstaller"
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
python -m PyInstaller --clean --noconfirm "packaging/jtagconn.spec"

$exePath = Join-Path $RepoRoot "dist\JTAG-conn.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected output not found: $exePath"
}
Write-Host "==> Built: $exePath"

if (-not $SkipInstaller) {
    $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($null -ne $iscc) {
        Write-Host "==> Building installer with Inno Setup"
        & $iscc.Source "packaging\installer.iss"
    } else {
        Write-Warning "ISCC.exe not found on PATH; skipping installer build."
    }
}

Write-Host "==> Done"
