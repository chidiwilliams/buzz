# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = []
datas += collect_data_files('torch')
datas += copy_metadata('tqdm')
datas += copy_metadata('torch')
datas += copy_metadata('regex')
datas += copy_metadata('requests')
datas += copy_metadata('packaging')
datas += copy_metadata('filelock')
datas += copy_metadata('numpy')
datas += copy_metadata('tokenizers')
datas += collect_data_files('whisper')


block_cipher = None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['apiclient', 'pyaudio', 'pytorch', '“sklearn.utils._cython_blas”', '“sklearn.neighbors.typedefs”',
                   '“sklearn.neighbors.quad_tree”', '“sklearn.tree”', '“sklearn.tree._utils”'],
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
    [],
    exclude_binaries=True,
    name='Buzz',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    upx=True,
    upx_exclude=[],
    name='Buzz',
)
app = BUNDLE(
    coll,
    name='Buzz.app',
    icon=None,
    bundle_identifier=None,
    version='0.0.1',
    info_plist={
        'NSMicrophoneUsageDescription': 'Please provide microphone access to continue'
    }
)
