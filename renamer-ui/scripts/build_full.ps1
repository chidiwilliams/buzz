#Requires -Version 5.1
<#
.SYNOPSIS
    Full build script for Buzz Renamer - Python backend + Electron installer.
.DESCRIPTION
    Builds a self-contained distributable of the Buzz Renamer Electron app,
    bundling the complete Python backend (including torch, whisper, faster-whisper,
    PyQt6) via PyInstaller, then packaging with electron-builder.
.HOW TO RUN
    Open PowerShell and navigate to the project root, then run:
    powershell -NoProfile -ExecutionPolicy Bypass -File renamer-ui\scripts\build_full.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---- Resolve paths -----------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$RenamerUI   = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $RenamerUI

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Buzz Renamer -- Full Build (torch + whisper)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Project root : $ProjectRoot"
Write-Host "  Renamer UI   : $RenamerUI"
Write-Host ""

# ---- Ensure Node.js is on PATH -----------------------------------------------
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $nodePath = 'C:\Program Files\nodejs'
    if (Test-Path "$nodePath\node.exe") {
        $env:PATH = "$nodePath;$env:PATH"
        Write-Host "[info] Added $nodePath to PATH" -ForegroundColor Yellow
    } else {
        Write-Error "Node.js not found. Install from https://nodejs.org and retry."
        exit 1
    }
}

# ---- Locate venv Python / PyInstaller ----------------------------------------
$VenvPy          = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$VenvPyInstaller = Join-Path $ProjectRoot '.venv\Scripts\pyinstaller.exe'

if (-not (Test-Path $VenvPy)) {
    Write-Error "Virtual environment not found at $VenvPy`nRun: uv sync  (or: pip install -e .)"
    exit 1
}

# ---- Step 1: Install websockets ----------------------------------------------
Write-Host ""
Write-Host "[Step 1/4] Ensuring websockets is installed..." -ForegroundColor Green
& $VenvPy -m pip install websockets --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "pip install websockets failed"; exit 1 }

# ---- Step 2: PyInstaller full build ------------------------------------------
Write-Host ""
Write-Host "[Step 2/4] Building Python backend (FULL - includes torch/whisper)..." -ForegroundColor Green
Write-Host "           This takes 10-20 minutes on first run." -ForegroundColor Yellow
Write-Host ""

Push-Location $ProjectRoot
try {
    $SpecFile = Join-Path $ProjectRoot 'renamer_backend_full.spec'

    if (-not (Test-Path $SpecFile)) {
        Write-Error "Spec file not found: $SpecFile"
        exit 1
    }

    & $VenvPyInstaller `
        --noconfirm `
        --distpath (Join-Path $ProjectRoot 'dist') `
        --workpath (Join-Path $ProjectRoot 'build\pyinstaller_work') `
        $SpecFile

    if ($LASTEXITCODE -ne 0) {
        Write-Error "[Step 2/4] PyInstaller failed (exit code $LASTEXITCODE)"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "[Step 2/4] Backend built successfully." -ForegroundColor Green

# ---- Step 3: npm install -----------------------------------------------------
Write-Host ""
Write-Host "[Step 3/4] Installing Electron dependencies..." -ForegroundColor Green
Push-Location $RenamerUI
try {
    & npm install --prefer-offline
    if ($LASTEXITCODE -ne 0) { Write-Error "npm install failed"; exit 1 }
} finally {
    Pop-Location
}

# ---- Step 4: electron-builder ------------------------------------------------
Write-Host ""
Write-Host "[Step 4/4] Packaging Electron app (zip + portable)..." -ForegroundColor Green
Write-Host "           No code signing (no certificate configured)." -ForegroundColor Yellow
Write-Host ""

$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'

# Pre-flight: make sure the Python backend was actually built
$BackendDir = Join-Path $ProjectRoot 'dist\renamer_backend'
if (-not (Test-Path $BackendDir)) {
    Write-Error "renamer_backend not found at $BackendDir - did PyInstaller succeed?"
    exit 1
}
Write-Host "  Backend found: $BackendDir" -ForegroundColor Green

Push-Location $RenamerUI
try {
    # build:win:full uses zip target only (no NSIS/portable -- both fail on 6GB bundles)
    $proc = Start-Process -FilePath 'npm' -ArgumentList 'run','build:win:full' `
        -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Host ""
        Write-Host "ERROR: electron-builder failed with exit code $($proc.ExitCode)" -ForegroundColor Red
        Write-Host "Tip: scroll up to see the full error from electron-builder." -ForegroundColor Yellow
        exit 1
    }
} finally {
    Pop-Location
}

# ---- Summary -----------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Output files:" -ForegroundColor White

$DistDir = Join-Path $RenamerUI 'dist'
Get-ChildItem -Path $DistDir -File |
    Where-Object { $_.Name -match '^Buzz Renamer' } |
    ForEach-Object {
        $sizeMB = [math]::Round($_.Length / 1MB, 1)
        Write-Host ("  {0,8} MB   {1}" -f $sizeMB, $_.Name) -ForegroundColor Cyan
    }

Write-Host ""
Write-Host "  Distribute either file - no installation required on target machine." -ForegroundColor Yellow
Write-Host "  The portable .exe is a single-file self-extracting runner." -ForegroundColor Yellow
Write-Host ""
