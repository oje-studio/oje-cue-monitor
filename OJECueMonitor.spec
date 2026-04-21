import os
import sys

# ── Detect libltc and portaudio paths (Apple Silicon vs Intel) ────────────────
def find_dylib(names):
    """Return (src_path, dest_dir) for the first found dylib."""
    search = ["/opt/homebrew/lib", "/usr/local/lib"]
    for name in names:
        for d in search:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return (p, ".")
    return None

ltc      = find_dylib(["libltc.dylib", "libltc.1.dylib"])
portaudio = find_dylib(["libportaudio.dylib", "libportaudio.2.dylib"])

binaries = []
if ltc:
    binaries.append(ltc)
if portaudio:
    binaries.append(portaudio)

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=[
        ("example_cues.csv", "."),
        ("example_show.ojeshow", "."),
        ("ui/", "ui/"),
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
    name="OJECueMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,     # no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.icns",   # uncomment and add icon.icns to use a custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OJECueMonitor",
)

# ── macOS .app bundle ─────────────────────────────────────────────────────────
app = BUNDLE(
    coll,
    name="ØJE CUE MONITOR.app",
    # icon="icon.icns",  # uncomment to use a custom icon
    bundle_identifier="studio.oje.cuemonitor",
    version="0.97.0",
    info_plist={
        "CFBundleDisplayName":          "ØJE CUE MONITOR",
        "CFBundleName":                 "ØJE CUE MONITOR",
        "CFBundleShortVersionString":   "0.97",
        "CFBundleVersion":              "0.97.0",
        "NSMicrophoneUsageDescription": "ØJE CUE MONITOR needs microphone access to receive LTC timecode from the audio input.",
        "NSHighResolutionCapable":      True,
        "LSUIElement":                  False,
        "NSRequiresAquaSystemAppearance": False,  # allow dark mode
    },
)
