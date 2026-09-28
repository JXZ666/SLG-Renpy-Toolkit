# -*- mode: python ; coding: utf-8 -*-
"""Console CLI executable. Build via build_exe.bat for version metadata."""

import os
from PyInstaller.utils.hooks import collect_submodules

version_file = os.environ.get("RPYKIT_CLI_VERSION_FILE")
if not version_file or not os.path.isfile(version_file):
    raise SystemExit("Build CLI through build_exe.bat (version resource missing).")

a = Analysis(
    ['app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    # fontTools resolves its table classes by tag at runtime, so static analysis
    # does not find them; the whole package is 4.4 MB, which is cheaper than
    # guessing which submodules the merge path touches.
    hiddenimports=collect_submodules('fontTools'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cmd_translate', 'cmd_skeleton', 'cmd_adopt', 'cmd_build', 'cmd_catalog', 'cmd_init', 'cmd_names', 'cmd_unpack', 'engine', 'conf'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

build_mode = (os.environ.get("RPYKIT_BUILD_MODE") or "onedir").strip().lower()
if build_mode not in ("onedir", "onefile"):
    raise SystemExit(
        "RPYKIT_BUILD_MODE must be 'onedir' or 'onefile', got %r" % build_mode
    )

if build_mode == "onefile":
    # Self-extracting single executable: binaries and datas go straight into the
    # EXE. Never pass exclude_binaries=True here - that flag is onedir's contract
    # and silently produces a broken onefile build.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='SLG-Renpy-Toolkit-CLI',
        icon='assets/SLG-Renpy-Toolkit.ico',
        version=version_file,
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
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='SLG-Renpy-Toolkit-CLI',
        icon='assets/SLG-Renpy-Toolkit.ico',
        version=version_file,
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
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='SLG-Renpy-Toolkit-CLI',
    )
