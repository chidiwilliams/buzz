# -*- mode: python ; coding: utf-8 -*-
import os
import platform

def find_dependency(name):
    """Find a binary on PATH, checking Chocolatey shim locations too."""
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe_path = os.path.join(path, name)
        if os.path.isfile(exe_path):
            return exe_path
        shim = os.path.normpath(
            os.path.join(path, "..", "lib", "ffmpeg", "tools", "ffmpeg", "bin", name)
        )
        if os.path.isfile(shim):
            return shim
    return None

# Sample audio file bundled alongside the exe so it always works
SAMPLE_SRC = os.path.join(
    os.path.dirname(os.path.abspath(SPEC)),  # buzz-audio-test/
    "..", "whisper.cpp", "samples", "jfk.wav"
)

binaries = []
datas = [(SAMPLE_SRC, "samples")]

if platform.system() == "Windows":
    ffmpeg = find_dependency("ffmpeg.exe")
    ffprobe = find_dependency("ffprobe.exe")
else:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

if ffmpeg:
    binaries.append((ffmpeg, "."))
if ffprobe:
    binaries.append((ffprobe, "."))

a = Analysis(
    [os.path.join(os.path.dirname(os.path.abspath(SPEC)), "audio_test.py")],
    pathex=[os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "sounddevice",
        "_sounddevice_data",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy ML deps not needed here
        "torch", "torchaudio", "transformers", "faster_whisper",
        "whisper", "ctranslate2", "numpy.distutils",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="BuzzAudioTest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,   # console=True so any startup errors are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    onefile=True,
)
