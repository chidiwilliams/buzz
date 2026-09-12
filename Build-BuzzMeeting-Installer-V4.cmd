@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Buzz Meeting - Build and Install Validated Windows Version V4

set "REPO=%~dp0."
set "CURRENT_BRANCH="
set "CURRENT_SHA="
set "REMOTE_SHA="
powershell.exe -NoProfile -NonInteractive -Command "$value = [Environment]::GetEnvironmentVariable('BUZZ_VALIDATED_SHA', 'Process'); if ($null -eq $value -or $value -cnotmatch '\A[0-9A-Fa-f]{40}\z') { exit 1 }"
if errorlevel 1 goto :usage
set "EXPECTED_SHA=%BUZZ_VALIDATED_SHA%"
for %%I in ("%REPO%") do set "REPO=%%~fI"
set "EXPECTED_INSTALLER=dist\Buzz-1.4.5-windows.exe"
set "GIT_BASH=C:\Program Files\Git\bin\bash.exe"
set "CTC_RUFF_CACHE=ctc_forced_aligner\.ruff_cache"

echo.
echo ============================================================
echo  Buzz Meeting - Build validated Windows installer V4
echo  Target commit: %EXPECTED_SHA%
echo ============================================================
echo.

if not exist "%REPO%\.git" (
  echo [ERROR] Repository not found:
  echo         %REPO%
  goto :fail
)
cd /d "%REPO%" || goto :fail

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git is not available on PATH.
  goto :fail
)

for /f "delims=" %%I in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%I"
if /I not "%CURRENT_BRANCH%"=="main" (
  echo [ERROR] Checkout is not on branch main.
  echo Current branch: %CURRENT_BRANCH%
  goto :fail
)

git diff --quiet --ignore-submodules=dirty
if errorlevel 1 (
  echo [ERROR] Tracked root-repository files have local modifications.
  git status --short
  goto :fail
)

git diff --cached --quiet --ignore-submodules=dirty
if errorlevel 1 (
  echo [ERROR] Staged root-repository changes exist.
  git status --short
  goto :fail
)

echo [1/8] Checking authoritative remote main...
git fetch origin refs/heads/main:refs/remotes/origin/main
if errorlevel 1 goto :buildfail

for /f "delims=" %%I in ('git rev-parse origin/main 2^>nul') do set "REMOTE_SHA=%%I"
if /I not "%REMOTE_SHA%"=="%EXPECTED_SHA%" (
  echo [ERROR] origin/main is no longer the validated target.
  echo Expected: %EXPECTED_SHA%
  echo Remote:   %REMOTE_SHA%
  goto :fail
)

for /f "delims=" %%I in ('git rev-parse HEAD 2^>nul') do set "CURRENT_SHA=%%I"
if /I not "%CURRENT_SHA%"=="%EXPECTED_SHA%" (
  git merge-base --is-ancestor HEAD origin/main
  if errorlevel 1 (
    echo [ERROR] Local main is not a simple ancestor of validated origin/main.
    goto :fail
  )
  git merge --ff-only origin/main
  if errorlevel 1 goto :buildfail
)

for /f "delims=" %%I in ('git rev-parse HEAD 2^>nul') do set "CURRENT_SHA=%%I"
if /I not "%CURRENT_SHA%"=="%EXPECTED_SHA%" (
  echo [ERROR] Local HEAD did not reach validated target.
  goto :fail
)

echo Local source:
echo   %CURRENT_SHA%

where uv >nul 2>nul
if errorlevel 1 (
  echo [ERROR] uv is not available on PATH.
  goto :fail
)
where make >nul 2>nul
if errorlevel 1 (
  echo [ERROR] GNU make is not available on PATH.
  goto :fail
)
where cmake >nul 2>nul
if errorlevel 1 (
  echo [ERROR] CMake is not available on PATH.
  goto :fail
)
if not exist "%GIT_BASH%" (
  echo [ERROR] Git Bash was not found:
  echo         %GIT_BASH%
  goto :fail
)

where iscc >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "PATH=%ProgramFiles(x86)%\Inno Setup 6;%PATH%"
  ) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "PATH=%ProgramFiles%\Inno Setup 6;%PATH%"
  )
)
where iscc >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Inno Setup 6 compiler ^(ISCC.exe^) was not found.
  goto :fail
)

echo.
echo [2/8] Initializing repository submodules...
git submodule update --init --recursive
if errorlevel 1 goto :buildfail

echo.
echo [3/8] Synchronizing Python dependencies...
uv sync
if errorlevel 1 goto :buildfail

echo.
echo [4/8] Removing ONLY the known Ruff cache if present...
if exist "%CTC_RUFF_CACHE%" (
  for /f "delims=" %%I in ('git -C ctc_forced_aligner ls-files .ruff_cache 2^>nul') do (
    echo [ERROR] Refusing to remove .ruff_cache because it contains a tracked path:
    echo         %%I
    goto :fail
  )

  echo Found untracked CTC Ruff cache:
  echo   %REPO%\%CTC_RUFF_CACHE%
  echo Removing that cache only...
  rmdir /s /q "%CTC_RUFF_CACHE%"
  if exist "%CTC_RUFF_CACHE%" (
    echo [ERROR] Could not remove the Ruff cache.
    goto :fail
  )
) else (
  echo No CTC Ruff cache is present.
)

echo.
echo CTC state after targeted cache removal:
git -C ctc_forced_aligner status --short

echo.
echo [5/8] Preparing packaged DLL backup...
if exist "dll_backup" (
  if not exist "buzz\dll_backup" mkdir "buzz\dll_backup" >nul 2>nul
  xcopy "dll_backup\*" "buzz\dll_backup\" /E /I /Y /Q >nul
  if errorlevel 2 goto :buildfail
) else (
  echo [WARN] dll_backup directory was not found; continuing.
)

echo.
echo [6/8] Verifying Git Bash build tools...
rem Git Bash inherits the validated repository working directory above.
"%GIT_BASH%" -c "command -v uname && command -v mktemp && command -v uv && command -v make && command -v cmake"
if errorlevel 1 (
  echo [ERROR] Git Bash cannot see one or more required tools.
  goto :fail
)

echo.
echo [7/8] Building Windows application and installer inside Git Bash...
"%GIT_BASH%" -c "uv run make bundle_windows"
if errorlevel 1 goto :buildfail

echo.
echo [8/8] Verifying and opening installer...
if not exist "%EXPECTED_INSTALLER%" (
  echo [ERROR] Packaging returned success but installer is missing:
  echo   %REPO%\%EXPECTED_INSTALLER%
  goto :fail
)

echo.
echo ============================================================
echo  SUCCESS
echo.
echo  Installer:
echo  %REPO%\%EXPECTED_INSTALLER%
echo.
echo  - Start-menu shortcut is created automatically.
echo  - Tick "Create a desktop icon" for a desktop shortcut.
echo  - After installation, no command line is needed.
echo ============================================================
echo.

start "" "%REPO%\%EXPECTED_INSTALLER%"
exit /b 0

:buildfail
echo.
echo [ERROR] The update/build process failed.
echo No git reset, git clean, stash, commit, or push was performed.
echo Only ctc_forced_aligner\.ruff_cache may have been removed.
echo Review the last error lines above.
goto :fail

:fail
echo.
exit /b 1

:usage
echo Set BUZZ_VALIDATED_SHA to the full 40-character validated origin/main commit SHA.
echo Example: set "BUZZ_VALIDATED_SHA=0123456789abcdef0123456789abcdef01234567" ^&^& %~nx0
exit /b 1
