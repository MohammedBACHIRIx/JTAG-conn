Param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

# Prefer standard Python 3.12+ launcher (`py -3.12` / `py -3`) or existing `.venv`
# instead of embedded toolchains (like TyphoonSim's GCC python) that may sit on PATH.
function Resolve-BasePython {
    if (Get-Command "py.exe" -ErrorAction SilentlyContinue) {
        try {
            $p = & py.exe -3.12 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path $p.Trim())) {
                return $p.Trim()
            }
        } catch {}
        try {
            $p = & py.exe -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path $p.Trim())) {
                return $p.Trim()
            }
        } catch {}
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python313\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            return $c
        }
    }
    $cmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return $cmd.Source
    }
    throw "Python 3.12+ was not found. Install Python 3.12 from https://www.python.org/downloads/windows/"
}

$VenvDir = Join-Path $RepoRoot ".venv-win"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    $BasePython = Resolve-BasePython
    Write-Host "==> Using base Python: $BasePython"
    Write-Host "==> Creating isolated build virtual environment at $VenvDir"
    & $BasePython -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) {
        throw "Failed to create virtual environment at $VenvDir"
    }
}

Write-Host "==> Using build Python: $VenvPython"
Write-Host "==> Installing dependencies (including PySide6, pyelftools, pydantic, pyinstaller)"
& $VenvPython -m pip install --upgrade pip wheel setuptools
& $VenvPython -m pip install -e ".[dev]" pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "pip install failed with exit code $LASTEXITCODE"
}

if (-not $SkipTests) {
    Write-Host "==> Running tests"
    $env:QT_QPA_PLATFORM = "offscreen"
    & $VenvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE"
    }
}

Write-Host "==> Building single-file JTAG-conn.exe with PyInstaller"
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
& $VenvPython -m PyInstaller --clean --noconfirm "packaging/jtagconn.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$exePath = Join-Path $RepoRoot "dist\JTAG-conn.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected output not found: $exePath"
}
Write-Host "==> Built standalone single-file executable: $exePath"

if (-not $SkipInstaller) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) {
        $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if ($null -ne $cmd) { $iscc = $cmd.Source } else { $iscc = $null }
    }
    if ($null -ne $iscc -and (Test-Path $iscc)) {
        Write-Host "==> Building installer with Inno Setup ($iscc)"
        & $iscc "packaging\installer.iss"
    } else {
        Write-Warning "ISCC.exe not found; skipping JTAG-conn-Setup.exe installer build (standalone dist\JTAG-conn.exe is ready)."
    }
}

Write-Host "==> Done! Executable is at: $exePath"
