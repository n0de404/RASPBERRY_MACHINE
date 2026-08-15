# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path.cwd()
datas = [
    (str(project_dir / "Animations"), "Animations"),
    (str(project_dir / "Images"), "Images"),
    (str(project_dir / "PDR_Icon"), "PDR_Icon"),
    (str(project_dir / "digital-7.ttf"), "."),
    (str(project_dir / "bgsteel.jpg"), "."),
]

# Runtime databases, queues, sessions, settings, and caches deliberately remain
# outside the executable. The Pi launcher points MACHINE_DATA_DIR at a durable
# per-device directory and initializes safe seeds there on first installation.

hiddenimports = [
    "mappings",
    "ui_theme",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "requests",
    "qrcode",
    "PIL",
    "PIL.Image",
    "pymysql",
    "pymysql.cursors",
    "serial",
]


a = Analysis(
    ["client.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
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
    a.binaries,
    a.datas,
    [],
    name="RaspberryMachineClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
