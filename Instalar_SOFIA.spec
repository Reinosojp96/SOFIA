# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['instalar_sofia.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['urllib.request', 'zipfile', 'pathlib', 'subprocess', 'threading'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Instalar_SOFIA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='_version_info.txt',
    uac_admin=True,
)
