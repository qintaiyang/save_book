# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = (
    collect_submodules('PyQt6.QtWebEngineCore')
    + collect_submodules('PyQt6.QtWebEngineWidgets')
    + collect_submodules('PyQt6.QtWebChannel')
)


a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('adb', 'adb'), ('qidian_save/desktop/style', 'qidian_save/desktop/style')],
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='qidian-save',
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
    icon='qidian_save/desktop/assets/dianbei.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='qidian-save',
)
