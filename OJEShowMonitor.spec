import os

# ── Entry point — runs the package as a module via a tiny shim ────────────────
# PyInstaller doesn't run entry points via `-m`, so we use a bootstrap script
# that imports show_monitor.main and calls it. Keeps the package self-contained.

SHIM_PATH = "_show_monitor_entry.py"
if not os.path.exists(SHIM_PATH):
    with open(SHIM_PATH, "w", encoding="utf-8") as f:
        f.write("from show_monitor.main import main\n"
                "import sys\n"
                "sys.exit(main())\n")

# ── Detect libltc and portaudio paths (Apple Silicon vs Intel) ────────────────
def find_dylib(names):
    search = ["/opt/homebrew/lib", "/usr/local/lib"]
    for name in names:
        for d in search:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return (p, ".")
    return None

ltc       = find_dylib(["libltc.dylib", "libltc.1.dylib"])
portaudio = find_dylib(["libportaudio.dylib", "libportaudio.2.dylib"])

binaries = []
if ltc:
    binaries.append(ltc)
if portaudio:
    binaries.append(portaudio)

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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OJEShowMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join("assets", "icon.icns"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OJEShowMonitor",
)

app = BUNDLE(
    coll,
    name="ØJE SHOW MONITOR.app",
    icon=os.path.join("assets", "icon.icns"),
    bundle_identifier="studio.oje.showmonitor",
    version="0.1.0",
    info_plist={
        "CFBundleDisplayName":          "ØJE SHOW MONITOR",
        "CFBundleName":                 "ØJE SHOW MONITOR",
        "CFBundleShortVersionString":   "0.1",
        "CFBundleVersion":              "0.1.0",
        "NSHumanReadableCopyright":     "© 2026 ØJE Studio · oje.studio · hello@oje.studio",
        "NSHighResolutionCapable":      True,
        "LSUIElement":                  False,
        "NSRequiresAquaSystemAppearance": False,
    },
)
