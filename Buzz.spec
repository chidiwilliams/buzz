# -*- mode: python ; coding: utf-8 -*-
import os
import os.path
import platform
import shutil

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

from buzz.__version__ import VERSION

datas = []
datas += collect_data_files("torch")
datas += collect_data_files("demucs")
datas += copy_metadata("tqdm")
datas += copy_metadata("torch")
datas += copy_metadata("regex")
datas += copy_metadata("requests")
datas += copy_metadata("packaging")
datas += copy_metadata("filelock")
datas += copy_metadata("numpy")
datas += copy_metadata("tokenizers")
datas += copy_metadata("huggingface-hub")
datas += copy_metadata("safetensors")
datas += copy_metadata("pyyaml")

# Allow transformers package to load __init__.py file dynamically:
# https://github.com/chidiwilliams/buzz/issues/272
datas += collect_data_files("transformers", include_py_files=True)

datas += collect_data_files("faster_whisper", include_py_files=True)
datas += collect_data_files("stable_whisper", include_py_files=True)
datas += collect_data_files("whisper")
datas += collect_data_files("demucs", include_py_files=True)
datas += collect_data_files("whisper_diarization", include_py_files=True)
datas += [("buzz/assets/*", "assets")]
datas += [("buzz/locale", "locale")]
datas += [("buzz/schema.sql", ".")]

block_cipher = None

DEBUG = os.environ.get("PYINSTALLER_DEBUG", "").lower() in ["1", "true"]
if DEBUG:
    options = [("v", None, "OPTION")]
else:
    options = []

def find_dependency(name: str) -> str:
    paths = os.environ["PATH"].split(os.pathsep)
    candidates = []
    for path in paths:
        exe_path = os.path.join(path, name)
        if os.path.isfile(exe_path):
            candidates.append(exe_path)

        # Check for chocolatery shims
        shim_path = os.path.normpath(os.path.join(path, "..", "lib", "ffmpeg", "tools", "ffmpeg", "bin", name))
        if os.path.isfile(shim_path):
            candidates.append(shim_path)

    if not candidates:
        return None

    # Pick the largest file
    return max(candidates, key=lambda f: os.path.getsize(f))

if platform.system() == "Windows":
    binaries = [
        (find_dependency("ffmpeg.exe"), "."),
        (find_dependency("ffprobe.exe"), "."),
    ]
else:
    binaries = [
        (shutil.which("ffmpeg"), "."),
        (shutil.which("ffprobe"), "."),
    ]

binaries.append(("buzz/whisper_cpp/*", "buzz/whisper_cpp"))

if platform.system() == "Windows":
    datas += [("dll_backup", "dll_backup")]
    datas += collect_data_files("msvc-runtime")

    binaries.append(("dll_backup/SDL2.dll", "dll_backup"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    options,
    icon="./assets/buzz.ico",
    exclude_binaries=True,
    name="Buzz",
    debug=DEBUG,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=DEBUG,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=os.environ.get("BUZZ_CODESIGN_IDENTITY"),
    entitlements_file="entitlements.plist" if platform.system() == "Darwin" else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Buzz",
)
app = BUNDLE(
    coll,
    name="Buzz.app",
    icon="./assets/buzz.icns",
    bundle_identifier="com.chidiwilliams.buzz",
    version=VERSION,
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": "True",
        "NSMicrophoneUsageDescription": "Allow Buzz to record audio from your microphone.",
    },
)
