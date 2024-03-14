# -*- mode: python ; coding: utf-8 -*-
import os.path
import platform
import shutil

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = []
datas += collect_data_files("torch")
datas += copy_metadata("tqdm")
datas += copy_metadata("torch")
datas += copy_metadata("regex")
datas += copy_metadata("requests")
datas += copy_metadata("packaging")
datas += copy_metadata("filelock")
datas += copy_metadata("numpy")
datas += copy_metadata("tokenizers")

# Allow transformers package to load __init__.py file dynamically:
# https://github.com/chidiwilliams/buzz/issues/272
datas += collect_data_files("transformers", include_py_files=True)

datas += collect_data_files("whisper")
datas += [("buzz/assets/*", "assets")]
datas += [
    (file[1], os.path.dirname(file[1]))
    for file in Tree("./buzz/locale", prefix="buzz/locale", excludes=["*.po"])
]

block_cipher = None

DEBUG = os.environ.get("PYINSTALLER_DEBUG", "").lower() in ["1", "true"]
if DEBUG:
    options = [("v", None, "OPTION")]
else:
    options = []

binaries = [
    (
        "buzz/whisper.dll" if platform.system() == "Windows" else "buzz/libwhisper.*",
        ".",
    ),
    (shutil.which("ffmpeg"), "."),
    (shutil.which("ffprobe"), "."),
]

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
    codesign_identity=None,
    entitlements_file=None,
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
    version="0.8.4",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": "True",
        "NSMicrophoneUsageDescription": "Allow Buzz to record audio from your microphone.",
    },
)
