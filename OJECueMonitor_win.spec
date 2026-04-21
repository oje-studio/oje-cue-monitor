import os
import sys

# ── Locate libltc.dll ────────────────────────────────────────────────────────
dll_path = os.path.join("libs", "win64", "libltc.dll")
if not os.path.exists(dll_path):
    print(f"ERROR: {dll_path} not found. Place libltc.dll in libs/win64/")
    sys.exit(1)

binaries = [
    (dll_path, "."),
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[
        ("example_cues.csv", "."),
        ("example_show.ojeshow", "."),
    ],
    hiddenimports=[
        "pyaudio",
        "numpy",
        "numpy.core._multiarray_umath",
        "ctypes",
        "ctypes.util",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ── Single-file .exe ─────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OJE CUE MONITOR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    # icon="icon.ico",
    version="version_info_win.txt",
)
