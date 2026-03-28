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
datas += copy_metadata("julius")
datas += copy_metadata("openunmix")
datas += copy_metadata("lameenc")
datas += copy_metadata("diffq")
datas += copy_metadata("einops")
datas += copy_metadata("hydra-core")
datas += copy_metadata("hydra-colorlog")
datas += copy_metadata("museval")
datas += copy_metadata("submitit")
datas += copy_metadata("treetable")
datas += copy_metadata("soundfile")
datas += copy_metadata("dora-search")
datas += copy_metadata("lhotse")

# Allow transformers package to load __init__.py file dynamically:
# https://github.com/chidiwilliams/buzz/issues/272
datas += collect_data_files("transformers", include_py_files=True)

datas += collect_data_files("faster_whisper", include_py_files=True)
datas += collect_data_files("stable_whisper", include_py_files=True)
datas += collect_data_files("whisper")
datas += collect_data_files("demucs", include_py_files=True)
datas += collect_data_files("whisper_diarization", include_py_files=True)
datas += collect_data_files("deepmultilingualpunctuation", include_py_files=True)
datas += collect_data_files("ctc_forced_aligner", include_py_files=True, excludes=["build"])
datas += collect_data_files("nemo", include_py_files=True)
datas += collect_data_files("lightning_fabric", include_py_files=True)
datas += collect_data_files("pytorch_lightning", include_py_files=True)
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

# Bundle a standalone Python 3.12 interpreter for runtime pip installs (e.g. CUDA).
# We copy python.exe, DLLs, and the stdlib from the uv-managed base interpreter.
if platform.system() == "Windows":
    import sys as _sys
    _base = _sys.base_prefix  # e.g. .../uv/python/cpython-3.12.12-windows-x86_64-none
    _py_dest = "python"
    if os.path.isfile(os.path.join(_base, "python.exe")):
        binaries.append((os.path.join(_base, "python.exe"), _py_dest))
        binaries.append((os.path.join(_base, "python3.dll"), _py_dest))
        binaries.append((os.path.join(_base, "python312.dll"), _py_dest))
        for _vcrt in ("vcruntime140.dll", "vcruntime140_1.dll"):
            _vcrt_path = os.path.join(_base, _vcrt)
            if os.path.isfile(_vcrt_path):
                binaries.append((_vcrt_path, _py_dest))
        # Bundle DLLs directory (C extensions like _ssl, _socket, etc.)
        _dlls_dir = os.path.join(_base, "DLLs")
        if os.path.isdir(_dlls_dir):
            for _f in os.listdir(_dlls_dir):
                binaries.append((os.path.join(_dlls_dir, _f), os.path.join(_py_dest, "DLLs")))
        # Bundle standard library
        datas.append((os.path.join(_base, "Lib"), os.path.join(_py_dest, "Lib")))
    else:
        print(f"WARNING: Could not find bundleable Python at {_base}")

if platform.system() == "Windows":
    datas += [("dll_backup", "dll_backup")]
    datas += collect_data_files("msvc-runtime")

    binaries.append(("dll_backup/SDL2.dll", "dll_backup"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "dora", "dora.log",
        "julius", "julius.core", "julius.resample",
        "openunmix", "openunmix.filtering",
        "lameenc",
        "diffq",
        "einops",
        "hydra", "hydra.core", "hydra.core.global_hydra",
        "hydra_colorlog",
        "museval",
        "submitit",
        "treetable",
        "soundfile",
        "_soundfile_data",
        "lhotse",
    ],
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
    icon="./buzz/assets/buzz.ico",
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
    icon="./buzz/assets/buzz.icns",
    bundle_identifier="com.chidiwilliams.buzz",
    version=VERSION,
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": "True",
        "NSMicrophoneUsageDescription": "Allow Buzz to record audio from your microphone.",
    },
)
