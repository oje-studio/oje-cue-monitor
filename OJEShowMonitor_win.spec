import os

SHIM_PATH = "_show_monitor_entry.py"
if not os.path.exists(SHIM_PATH):
    with open(SHIM_PATH, "w", encoding="utf-8") as f:
        f.write("from show_monitor.main import main\n"
                "import sys\n"
                "sys.exit(main())\n")

# SHOW MONITOR doesn't (yet) use libltc — it's a world-clock app.
# Keep the same layout as the CUE MONITOR spec so a later LTC addition
# plugs in without reshuffling the build.
binaries = []

a = Analysis(
    [SHIM_PATH],
    pathex=["."],
    binaries=binaries,
    datas=[
        ("show_monitor/", "show_monitor/"),
        ("assets/icon.ico", "assets"),
        ("assets/icon.icns", "assets"),
        ("assets/icon_1024.png", "assets"),
    ],
    hiddenimports=[
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OJE SHOW MONITOR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join("assets", "icon.ico"),
)
