# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cmd_translate', 'cmd_skeleton', 'cmd_adopt', 'cmd_build', 'cmd_catalog', 'cmd_init', 'cmd_names', 'cmd_unpack', 'engine', 'conf'],
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
    name='SLG-Renpy-Toolkit',
    icon='assets/SLG-Renpy-Toolkit.ico',
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
)
