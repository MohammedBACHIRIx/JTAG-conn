# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

project_root = Path(SPECPATH).resolve().parent
src_path = project_root / "src"

hiddenimports = []
hiddenimports += collect_submodules("jtagconn")
hiddenimports += collect_submodules("PySide6")
hiddenimports += collect_submodules("elftools")
hiddenimports += collect_submodules("pydantic")

# Include CCXML generator/templates and any package data within jtagconn
_datas = []
ccxml_dir = src_path / "jtagconn" / "backend" / "ccxml"
if ccxml_dir.exists():
    _datas.append((str(ccxml_dir), "jtagconn/backend/ccxml"))

a = Analysis(
    [str(src_path / "jtagconn" / "app.py")],
    pathex=[str(project_root), str(src_path)],
    binaries=[],
    datas=_datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="JTAG-conn",
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
