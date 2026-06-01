@echo off
REM build_all.bat — Build the full Buzz Renamer installer
REM Can be run from any directory — double-click or call from CI.

setlocal enabledelayedexpansion

REM ── Resolve paths from this script's location ─────────────────────────────
set "SCRIPT_DIR=%~dp0"

REM renamer-ui dir = one level up from scripts\
pushd "%SCRIPT_DIR%.."
set "RENAMER_UI=%CD%"
popd

REM project root = two levels up from scripts\
pushd "%SCRIPT_DIR%..\..\"
set "PROJECT_ROOT=%CD%"
popd

echo ================================================
echo  Buzz Renamer -- Full Build
echo ================================================
echo  Script dir  : %SCRIPT_DIR%
echo  Project root: %PROJECT_ROOT%
echo  Renamer UI  : %RENAMER_UI%
echo ================================================
echo.

REM ── Ensure Node.js is on PATH ──────────────────────────────────────────────
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  REM Try the default install location
  if exist "C:\Program Files\nodejs\node.exe" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
    echo [info] Added C:\Program Files\nodejs to PATH
  ) else (
    echo ERROR: Node.js not found. Install from https://nodejs.org and retry.
    exit /b 1
  )
)

REM ── Step 1: Python backend ─────────────────────────────────────────────────
echo [Step 1/3] Building Python backend...
call "%SCRIPT_DIR%build_backend.bat"
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Python backend build failed.
  exit /b 1
)

REM ── Step 2: npm install ────────────────────────────────────────────────────
echo.
echo [Step 2/3] Installing / updating Electron dependencies...
pushd "%RENAMER_UI%"
call npm install --prefer-offline
if %ERRORLEVEL% NEQ 0 (
  popd
  echo ERROR: npm install failed.
  exit /b 1
)

REM ── Step 3: Build installer ────────────────────────────────────────────────
echo.
echo [Step 3/3] Packaging Electron installer (NSIS)...
REM Disable code signing — no certificate present.
REM WIN_CSC_LINK must be UNSET (not empty string) to skip Windows signing.
REM package.json also sets sign=null and signingHashAlgorithms=null.
set CSC_IDENTITY_AUTO_DISCOVERY=false
call npm run build:win
if %ERRORLEVEL% NEQ 0 (
  popd
  echo ERROR: electron-builder failed.
  exit /b 1
)
popd

echo.
echo ================================================
echo  Build complete!
echo  Installer : %RENAMER_UI%\dist\Buzz Renamer Setup*.exe
echo ================================================
endlocal
