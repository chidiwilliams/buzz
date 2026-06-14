@echo off
REM build_backend.bat — Build renamer_backend.exe with PyInstaller
REM Can be run from any directory — resolves paths using %~dp0.

REM Project root is two levels up from this script (scripts\ -> renamer-ui\ -> project root)
set "SCRIPT_DIR=%~dp0"

pushd "%SCRIPT_DIR%..\.."
set "PROJECT_ROOT=%CD%"
popd

echo [build_backend] Project root: %PROJECT_ROOT%
echo.

REM ── Install websockets ────────────────────────────────────────────────────────
echo [build_backend] Installing websockets dependency...
set "VENV_PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
  "%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
  "%VENV_PY%" -m pip install websockets --quiet
) else (
  where uv >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    uv pip install websockets
  ) else (
    python -m pip install websockets --quiet
  )
)

echo.
echo [build_backend] Building Python backend with PyInstaller...
echo [build_backend] (Excluding heavy ML libs to keep bundle size manageable)
echo.

pushd "%PROJECT_ROOT%"

set "PYINSTALLER=%PROJECT_ROOT%\.venv\Scripts\pyinstaller.exe"
if not exist "%PYINSTALLER%" set "PYINSTALLER=pyinstaller"

"%PYINSTALLER%" ^
  --noconfirm ^
  --onedir ^
  --name renamer_backend ^
  --distpath "%PROJECT_ROOT%\dist" ^
  --workpath "%PROJECT_ROOT%\build\pyinstaller_work" ^
  --hidden-import=buzz.transcriber.renamer_server ^
  --hidden-import=buzz.transcriber.bulk_renamer ^
  --hidden-import=buzz.transcriber.whisper_file_transcriber ^
  --hidden-import=buzz.transcriber.whisper_cpp ^
  --hidden-import=buzz.model_loader ^
  --hidden-import=buzz.whisper_audio ^
  --hidden-import=buzz.assets ^
  --hidden-import=buzz.locale ^
  --hidden-import=websockets ^
  --hidden-import=websockets.server ^
  --hidden-import=websockets.legacy.server ^
  --hidden-import=PyQt6.QtCore ^
  --hidden-import=whisper ^
  --hidden-import=faster_whisper ^
  --collect-submodules=buzz.transcriber ^
  --collect-submodules=buzz ^
  --collect-all=websockets ^
  --paths="%PROJECT_ROOT%" ^
  --exclude-module=torch ^
  --exclude-module=torchaudio ^
  --exclude-module=torchvision ^
  --exclude-module=torchcodec ^
  --exclude-module=bitsandbytes ^
  --exclude-module=transformers ^
  --exclude-module=accelerate ^
  --exclude-module=nemo ^
  --exclude-module=nemo_toolkit ^
  --exclude-module=datasets ^
  --exclude-module=scipy ^
  --exclude-module=matplotlib ^
  --exclude-module=sklearn ^
  --exclude-module=tensorflow ^
  --exclude-module=jax ^
  --exclude-module=wandb ^
  buzz\transcriber\renamer_server.py

if %ERRORLEVEL% NEQ 0 (
  popd
  echo.
  echo [build_backend] ERROR: PyInstaller failed.
  exit /b 1
)

popd

echo.
echo [build_backend] Done! Output: %PROJECT_ROOT%\dist\renamer_backend\
