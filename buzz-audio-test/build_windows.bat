@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  Buzz Audio Test - Windows Build Script
echo ============================================================
echo.

:: Move to the repo root (one level up from this script's directory)
pushd "%~dp0.."

:: Verify uv is available
where uv >nul 2>&1
if errorlevel 1 (
    echo ERROR: 'uv' not found on PATH.
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

:: Verify ffmpeg is available (needed by Qt multimedia at runtime)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo WARNING: 'ffmpeg' not found on PATH.
    echo The built exe will not be able to play audio unless ffmpeg is present.
    echo Install via: winget install ffmpeg   OR   choco install ffmpeg
    echo.
)

echo [1/3] Installing / syncing dependencies ...
uv sync
if errorlevel 1 ( echo FAILED: uv sync & exit /b 1 )

echo.
echo [2/3] Installing PyInstaller into the virtual environment ...
uv pip install pyinstaller
if errorlevel 1 ( echo FAILED: pip install pyinstaller & exit /b 1 )

echo.
echo [3/3] Building BuzzAudioTest.exe ...
uv run pyinstaller --clean --noconfirm buzz-audio-test\AudioTest.spec
if errorlevel 1 ( echo FAILED: pyinstaller & exit /b 1 )

echo.
echo ============================================================
echo  SUCCESS!
echo  Output: dist\BuzzAudioTest.exe
echo ============================================================

popd
endlocal
