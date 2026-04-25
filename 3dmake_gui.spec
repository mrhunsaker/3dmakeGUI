# 3dmake_gui.spec
# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller spec for producing a single-folder (or --onefile) build of the
# 3DMake GUI Wrapper.
#
# Usage (from the project root, with the venv active):
#
#   pyinstaller 3dmake_gui.spec
#
# Output is in dist/3dmake-gui/  (or dist/3dmake-gui.exe on Windows).
# ─────────────────────────────────────────────────────────────────────────────

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ── Collect NiceGUI's static web assets ──────────────────────────────────────
# NiceGUI ships JS/CSS/fonts inside its package; they must be bundled.
nicegui_datas = collect_data_files("nicegui", includes=["**/*"])

# pywebview also has assets (used for native window mode)
try:
    webview_datas = collect_data_files("webview")
except Exception:
    webview_datas = []

all_datas = nicegui_datas + webview_datas

# ── Hidden imports ─────────────────────────────────────────────────────────
# NiceGUI and uvicorn rely on dynamic imports that PyInstaller can't detect.
hidden = (
    collect_submodules("nicegui")
    + collect_submodules("uvicorn")
    + collect_submodules("starlette")
    + collect_submodules("fastapi")
    + collect_submodules("anyio")
    + [
        "engineio.async_drivers.asgi",
        "socketio.async_namespace",
        "socketio.async_server",
        "webview",          # pywebview native window
        "tdmake_gui_wrapper",
        "tdmake_gui_wrapper.app",
        "tdmake_gui_wrapper.core",
    ]
)

block_cipher = None

a = Analysis(
    ["src/tdmake_gui_wrapper/__main__.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=all_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="3dmake-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Set True if you want a terminal window alongside
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="docs/icon.ico",  # ← uncomment and point at your .ico file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="3dmake-gui",
)
