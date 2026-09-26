# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

# Biblioteka `holidays` (logic/utils/holidays_pl.py) - patrz ten sam
# komentarz w "Enyo - Grafik Pracy.spec".
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
    ('C:\\Users\\kewi1\\AppData\\Local\\Programs\\Python\\Python313\\python313.dll', '.'),
    ('C:\\Users\\kewi1\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\ortools\\.libs\\*.dll', 'ortools\\.libs')
    ],
    datas=[('assets', 'assets')] + collect_data_files('holidays'),
    hiddenimports=['ortools', 'ortools.sat', 'ortools.sat.python', 'ortools.sat.python.cp_model', 'holidays'],
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
    name='Dingo! - narzędzie do grafików pracy',
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
    icon=['dingo_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Dingo! - narzędzie do grafików pracy',
)
