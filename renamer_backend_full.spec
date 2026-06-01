# renamer_backend_full.spec
# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller spec for Buzz Renamer — FULL build
#
# Includes: torch, whisper, faster_whisper, PyQt6, ctranslate2, websockets,
#           buzz (all submodules + assets + locale + whisper_cpp binaries)
#
# Expected output size: ~4–6 GB (unpacked), ~1.5–3 GB (zip)
# Run via:  renamer-ui\scripts\build_full.ps1
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Project root (one level above renamer-ui\) ────────────────────────────────
# The spec lives in the project root when PyInstaller is invoked.
ROOT = Path(SPECPATH)

# ── Data files ───────────────────────────────────────────────────────────────
datas = []

# buzz assets (icons, SVGs, banner image)
datas += [(str(ROOT / 'buzz' / 'assets'), 'buzz/assets')]

# buzz locale (translations)
datas += [(str(ROOT / 'buzz' / 'locale'), 'buzz/locale')]

# whisper.cpp native binaries (whisper-cli.exe, whisper-server.exe, SDL2.dll, silero model)
datas += [(str(ROOT / 'buzz' / 'whisper_cpp'), 'buzz/whisper_cpp')]

# Pull in all data files from whisper (mel_filters.npz, multilingual.tiktoken, etc.)
datas += collect_data_files('whisper')

# ctranslate2 needs its CUDA / OpenMP DLLs collected
datas += collect_data_files('ctranslate2')

# faster_whisper assets
datas += collect_data_files('faster_whisper')

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = [
    # ── Buzz transcriber stack ──────────────────────────────────────
    'buzz.transcriber.renamer_server',
    'buzz.transcriber.bulk_renamer',
    'buzz.transcriber.whisper_file_transcriber',
    'buzz.transcriber.whisper_cpp_file_transcriber',
    'buzz.transcriber.faster_whisper_file_transcriber',
    'buzz.transcriber.transcriber',
    'buzz.transcriber.whisper_cpp',
    'buzz.model_loader',
    'buzz.whisper_audio',
    'buzz.assets',
    'buzz.locale',
    'buzz.settings',
    'buzz.store',
    # ── WebSocket server ────────────────────────────────────────────
    'websockets',
    'websockets.server',
    'websockets.legacy.server',
    'websockets.asyncio.server',
    # ── Qt (headless core only) ─────────────────────────────────────
    'PyQt6.QtCore',
    'PyQt6.QtNetwork',
    # ── Whisper backends ────────────────────────────────────────────
    'whisper',
    'faster_whisper',
    'ctranslate2',
    # ── Audio processing ────────────────────────────────────────────
    'soundfile',
    'av',
    'ffmpeg',
    # ── Misc runtime deps ───────────────────────────────────────────
    'huggingface_hub',
    'huggingface_hub.file_download',
    'tokenizers',
    'requests',
    'certifi',
]

# Collect all buzz submodules automatically
hiddenimports += collect_submodules('buzz')
hiddenimports += collect_submodules('websockets')
hiddenimports += collect_submodules('faster_whisper')

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / 'buzz' / 'transcriber' / 'renamer_server.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI-only Qt modules not needed for headless server
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtMultimedia',
        'PyQt6.QtWebEngineWidgets',
        # Development / test tools
        'pytest',
        'IPython',
        'notebook',
        'matplotlib',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── FIX: bundle the OpenSSL DLLs that match the interpreter's _ssl.pyd ─────────
# PyInstaller can otherwise auto-collect a *different* libcrypto/libssl from
# site-packages, which is ABI-incompatible with the interpreter's _ssl.pyd and
# fails at runtime with:
#   ImportError: DLL load failed while importing _ssl:
#   The specified procedure could not be found.
# We strip any auto-collected copies, then inject the ones that ship next to
# _ssl.pyd in <base_prefix>/DLLs (the set _ssl.pyd was actually built against).
_OPENSSL_DLLS = ("libcrypto-3-x64.dll", "libssl-3-x64.dll")
_PY_DLL_DIR = Path(sys.base_prefix) / "DLLs"

a.binaries = [
    b for b in a.binaries
    if os.path.basename(b[0]).lower() not in _OPENSSL_DLLS
]
for _dll in _OPENSSL_DLLS:
    _src = _PY_DLL_DIR / _dll
    if _src.is_file():
        a.binaries.append((_dll, str(_src), "BINARY"))
    else:
        raise SystemExit(
            f"[spec] Expected interpreter OpenSSL not found: {_src}\n"
            f"       _ssl will be mismatched. Check sys.base_prefix/DLLs."
        )

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='renamer_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX incompatible with many torch DLLs
    console=True,        # Must be True — server writes PORT: to stdout
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'buzz' / 'assets' / 'buzz.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='renamer_backend',
)
