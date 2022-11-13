# -*- mode: python ; coding: utf-8 -*-
import platform
import shutil

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
datas += [('whisper.dll' if platform.system() ==
           'Windows' else 'libwhisper.*', '.')]
datas += [('assets/buzz.ico', 'assets')]
datas += [('assets/buzz-icon-1024.png', 'assets')]
datas += [(shutil.which('ffmpeg'), '.')]


block_cipher = None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
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
    [],
    icon='./assets/buzz.ico',
    exclude_binaries=True,
    name='Buzz',
    debug=True,
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
    upx=False,
    upx_exclude=[],
    name='Buzz',
)
app = BUNDLE(
    coll,
    name='Buzz.app',
    icon='./assets/buzz.icns',
    bundle_identifier='com.chidiwilliams.buzz',
    version='0.5.7',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'NSMicrophoneUsageDescription': 'Allow Buzz to record audio from your microphone.'
    }
)
