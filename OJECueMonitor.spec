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
        # Bundle assets/ so QIcon and the studio logo are loadable from
        # the frozen bundle — the spec-level icon= only sets Finder/Dock.
        ("assets/icon.ico", "assets"),
        ("assets/icon.icns", "assets"),
        ("assets/icon_1024.png", "assets"),
        ("assets/logo_src.png", "assets"),
    ],
    hiddenimports=[
        "pyaudio",
        "numpy",
        "numpy.core._multiarray_umath",
        "ctypes",
        "ctypes.util",
        # Web remote server (aiohttp loads these lazily)
        "aiohttp",
        "aiohttp.web",
        "aiohttp.web_ws",
        "aiohttp.web_runner",
        # QR code generation for web remote (qrcode[pil] uses PIL backend)
        "qrcode",
        "qrcode.image.pil",
        "PIL",
        "PIL.Image",
        "PIL.PngImagePlugin",
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
    icon=os.path.join("assets", "icon.icns"),
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
    icon=os.path.join("assets", "icon.icns"),
    bundle_identifier="studio.oje.cuemonitor",
    version="1.0.0",
    info_plist={
        "CFBundleDisplayName":          "ØJE CUE MONITOR",
        "CFBundleName":                 "ØJE CUE MONITOR",
        "CFBundleShortVersionString":   "1.0",
        "CFBundleVersion":              "1.0.0",
        "NSHumanReadableCopyright":     "© 2026 ØJE Studio · oje.studio · hello@oje.studio",
        "NSMicrophoneUsageDescription": "ØJE CUE MONITOR needs microphone access to receive LTC timecode from the audio input.",
        "NSHighResolutionCapable":      True,
        "LSUIElement":                  False,
        "NSRequiresAquaSystemAppearance": False,  # allow dark mode
    },
)
