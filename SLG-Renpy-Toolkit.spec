# -*- mode: python ; coding: utf-8 -*-
"""Windowed GUI executable. Build via build_exe.bat for version metadata."""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

version_file = os.environ.get("RPYKIT_GUI_VERSION_FILE")
if not version_file or not os.path.isfile(version_file):
    raise SystemExit("Build GUI through build_exe.bat (version resource missing).")

a = Analysis(
    ['app_window.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')] + collect_data_files('customtkinter'),
    hiddenimports=collect_submodules('customtkinter'),
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
    [],
    exclude_binaries=True,
    name='SLG-Renpy-Toolkit',
    icon='assets/SLG-Renpy-Toolkit.ico',
    version=version_file,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SLG-Renpy-Toolkit',
)
