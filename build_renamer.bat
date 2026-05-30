@echo off
REM ============================================================================
REM  build_renamer.bat  --  One-click full build of Buzz Renamer (Windows)
REM ----------------------------------------------------------------------------
REM  Does EVERYTHING in one shot:
REM    1. Ensures Python build deps (pyinstaller, websockets) via uv
REM    2. Rebuilds the Python backend with PyInstaller (full spec:
REM       torch + whisper + faster-whisper + PyQt6), which now bundles the
REM       CORRECT OpenSSL DLLs (fixes the "_ssl ... procedure could not be
REM       found" backend-startup-timeout crash).
REM    3. Installs Electron deps (npm)
REM    4. Packages the Electron app (zip, x64) into OUTPUT_DIR.
REM
REM  Just double-click this file, or run it from a terminal. No arguments.
REM  First run takes ~15-25 min (PyInstaller + packaging); later runs reuse
REM  PyInstaller's cache and are faster.
REM ============================================================================

setlocal

REM ---- Config (change OUTPUT_DIR if you want the build somewhere else) --------
set "OUTPUT_DIR=D:\Renamer Electron"

REM ---- Resolve paths (project root = the folder this .bat lives in) -----------
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "RENAMER_UI=%ROOT%\renamer-ui"
set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
set "VENV_PYI=%ROOT%\.venv\Scripts\pyinstaller.exe"
set "SPEC=%ROOT%\renamer_backend_full.spec"

echo.
echo ================================================
echo   Buzz Renamer -- Full Build
echo ================================================
echo   Project root : %ROOT%
echo   Output dir   : %OUTPUT_DIR%
echo.

REM ---- Pre-flight ------------------------------------------------------------
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment not found at %ROOT%\.venv
  echo         Create it first:  uv sync
  goto :fail
)
if not exist "%SPEC%" (
  echo [ERROR] Spec file not found: %SPEC%
  goto :fail
)

REM ---- Ensure Node.js is on PATH ---------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\nodejs\node.exe" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
    echo [info] Added C:\Program Files\nodejs to PATH
  ) else (
    echo [ERROR] Node.js not found. Install from https://nodejs.org and retry.
    goto :fail
  )
)

REM ---- Close any running instance so packaging doesn't hit locked files ------
taskkill /IM "Buzz Renamer.exe" /F >nul 2>nul
taskkill /IM "renamer_backend.exe" /F >nul 2>nul

REM ---- Step 1/4: Python build deps (via uv, additive -- nothing removed) -----
echo.
echo [1/4] Ensuring Python build deps (pyinstaller, websockets) via uv...
where uv >nul 2>nul
if errorlevel 1 (
  echo [info] uv not found -- falling back to venv pip.
  "%VENV_PY%" -m pip install --quiet pyinstaller websockets
) else (
  uv pip install --python "%VENV_PY%" --quiet pyinstaller websockets
)
if errorlevel 1 ( echo [ERROR] Installing build deps failed & goto :fail )

REM ---- Step 2/4: PyInstaller backend ----------------------------------------
echo.
echo [2/4] Building Python backend with PyInstaller...
echo        (full spec -- torch/whisper; first run ~15-20 min)
pushd "%ROOT%"
"%VENV_PYI%" --noconfirm --distpath "%ROOT%\dist" --workpath "%ROOT%\build\pyinstaller_work" "%SPEC%"
set "PYI_ERR=%errorlevel%"
popd
if not "%PYI_ERR%"=="0" ( echo [ERROR] PyInstaller failed ^(exit %PYI_ERR%^) & goto :fail )
if not exist "%ROOT%\dist\renamer_backend\renamer_backend.exe" (
  echo [ERROR] Backend exe missing after build.
  goto :fail
)
echo [2/4] Backend built: %ROOT%\dist\renamer_backend\renamer_backend.exe

REM ---- Step 3/4: npm install -------------------------------------------------
echo.
echo [3/4] Installing Electron dependencies...
pushd "%RENAMER_UI%"
call npm install --prefer-offline --no-audit --no-fund
if errorlevel 1 ( echo [ERROR] npm install failed & popd & goto :fail )

REM ---- Step 4/4: electron-builder -> OUTPUT_DIR ------------------------------
echo.
echo [4/4] Packaging Electron app (zip, x64) into "%OUTPUT_DIR%"...
set "CSC_IDENTITY_AUTO_DISCOVERY=false"
call npx --no-install electron-builder --win zip --x64 -c.directories.output="%OUTPUT_DIR%"
set "EB_ERR=%errorlevel%"
popd
if not "%EB_ERR%"=="0" ( echo [ERROR] electron-builder failed ^(exit %EB_ERR%^) & goto :fail )

echo.
echo ================================================
echo   BUILD COMPLETE
echo ================================================
echo   Distributable : "%OUTPUT_DIR%\Buzz Renamer-1.0.0-win.zip"
echo   Run directly  : "%OUTPUT_DIR%\win-unpacked\Buzz Renamer.exe"
echo.
goto :end

:fail
echo.
echo *** BUILD FAILED -- see messages above. ***
endlocal
exit /b 1

:end
endlocal
exit /b 0
