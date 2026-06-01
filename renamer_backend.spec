# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['buzz.transcriber.renamer_server', 'buzz.transcriber.bulk_renamer', 'buzz.transcriber.whisper_file_transcriber', 'buzz.transcriber.whisper_cpp', 'buzz.model_loader', 'buzz.whisper_audio', 'buzz.assets', 'buzz.locale', 'websockets', 'websockets.server', 'websockets.legacy.server', 'PyQt6.QtCore', 'whisper', 'faster_whisper']
hiddenimports += collect_submodules('buzz.transcriber')
hiddenimports += collect_submodules('buzz')
tmp_ret = collect_all('websockets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['buzz\\transcriber\\renamer_server.py'],
    pathex=['C:\\Users\\idoci\\buzz'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchaudio', 'torchvision', 'torchcodec', 'bitsandbytes', 'transformers', 'accelerate', 'nemo', 'nemo_toolkit', 'datasets', 'scipy', 'matplotlib', 'sklearn', 'tensorflow', 'jax', 'wandb'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='renamer_backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='renamer_backend',
)
