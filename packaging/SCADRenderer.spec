# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for SCADRenderer.exe."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project = Path(SPECPATH).resolve().parent  # noqa: F821
datas = [
    (str(project / "scad-variants" / "viewer"), "viewer"),
    (
        str(project / "scad-variants" / "scadvariants" / "show-toast.ps1"),
        "scadvariants",
    ),
]
hiddenimports = (
    collect_submodules("scadvariants")
    + ["scad_drop", "scad_variants", "open_gallery", "slicer_action"]
)

a = Analysis(
    [str(project / "packaging" / "scad_renderer.py")],
    pathex=[
        str(project / "scad-drop"),
        str(project / "scad-variants"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SCADRenderer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="SCADRenderer",
)
