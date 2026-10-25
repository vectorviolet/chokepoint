# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for Chokepoint.

    pyinstaller chokepoint.spec --noconfirm

Produces a onedir bundle in ``dist/chokepoint/`` whose launcher is
``chokepoint`` (``chokepoint.exe`` on Windows). onedir is preferred over
onefile for a game: startup is instant (no per-launch temp extraction) and the
assets stay browsable next to the executable.

The ``assets/`` and ``config/`` trees are bundled as data and unpacked to the
bundle root (``sys._MEIPASS``); ``util.paths.resource_root`` + the startup
``os.chdir`` make every cwd-relative path resolve there, exactly as from source.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # noqa: F821 — injected by PyInstaller

# Runtime data trees the game loads by relative path.
datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "config"), "config"),
    # Attribution and license texts travel with every build (CC BY 3.0 for
    # the music requires the credit to accompany the distributed game).
    (str(ROOT / "CREDITS.md"), "."),
    (str(ROOT / "LICENSE"), "."),
    # pygamine's shared splash (standard_splash_media), resolved next to the
    # pygamine package rather than the game's assets/
    (str(ROOT / "src" / "pygamine" / "pygamine" / "branding"), "pygamine/branding"),
]

# Optional per-OS application icon. Windows: the committed packaging/icon.ico
# (scripts/make_icon.py can regenerate one from the logo, overwriting it).
# macOS: drop packaging/icon.icns yourself.
# Absent icons are fine — the build just uses the default.
icon = None
if sys.platform.startswith("win") and (ROOT / "packaging" / "icon.ico").exists():
    icon = str(ROOT / "packaging" / "icon.ico")
elif sys.platform == "darwin" and (ROOT / "packaging" / "icon.icns").exists():
    icon = str(ROOT / "packaging" / "icon.icns")

a = Analysis(
    ["__main__.py"],
    pathex=[str(ROOT / "src"), str(ROOT / "src" / "pygamine")],
    binaries=[],
    datas=datas,
    # pytmx's pygame loader is imported through a string in the base tilemap;
    # pin both so the module graph can't miss them.
    hiddenimports=["pytmx", "pytmx.util_pygame"],
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
    name="chokepoint",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="chokepoint",
)

# Also put the credits and license at the top of the bundle, next to the
# executable, where players actually look (the datas copies above sit in
# _internal/, which the macOS .app below carries).
import shutil  # noqa: E402
for doc in ("CREDITS.md", "LICENSE"):
    shutil.copy2(ROOT / doc, Path(DISTPATH) / "chokepoint" / doc)  # noqa: F821 -- injected by PyInstaller

# On macOS, also wrap the onedir bundle as a .app for a native double-click.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Chokepoint.app",
        icon=icon,
        bundle_identifier="com.umutcanekinci.chokepoint",
    )
