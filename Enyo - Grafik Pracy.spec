# -*- mode: python ; coding: utf-8 -*-
# Osobny plik .spec dla kanału Enyo (patrz release_channel.py,
# scripts/build_release.ps1 -Channel enyo) - kopia "Dingo! - narzędzie do
# grafików pracy.spec" z podmienioną nazwą wynikowego exe/folderu, żeby
# build dla klienta Enyo nigdy nie nadpisał/nie pomylił się z folderem
# dist\ Dingo, i żeby oba kanały dało się budować niezależnie bez ręcznego
# przełączania tego pliku.

from PyInstaller.utils.hooks import collect_data_files

# Biblioteka `holidays` (logic/utils/holidays_pl.py) - kod używa tylko
# samych dat świąt, nie ich nazw/tłumaczeń, ale pakuje jej dane (pliki
# lokalizacji .mo) i tak, defensywnie - żeby ewentualna przyszła zmiana w
# bibliotece (albo w tym, jak jej używamy) nie wywaliła się dopiero w
# gotowym exe.
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
    name='Enyo - Grafik Pracy',
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
    name='Enyo - Grafik Pracy',
)
