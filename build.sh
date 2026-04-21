#!/bin/bash
# Run with:  bash build.sh   or   ./build.sh
# Do NOT run with python3 — this is a shell script.
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ØJE CUE MONITOR  —  Build         ║"
echo "║   macOS  .app  bundle                ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Check PyInstaller ─────────────────────────────────────────────────────────
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "▶  Installing PyInstaller..."
    pip3 install pyinstaller
else
    echo "▶  PyInstaller: OK"
fi

# ── Clean previous build ──────────────────────────────────────────────────────
echo "▶  Cleaning previous build..."
rm -rf build dist

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo "▶  Building .app bundle..."
python3 -m PyInstaller OJECueMonitor.spec --noconfirm

# ── Result ────────────────────────────────────────────────────────────────────
APP="dist/ØJE CUE MONITOR.app"

if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo ""
    echo "══════════════════════════════════════════"
    echo "  ✓  Build successful!"
    echo ""
    echo "  App : $APP"
    echo "  Size: $SIZE"
    echo ""
    echo "  To open:"
    echo "    open \"$APP\""
    echo ""
    echo "  To copy to Applications:"
    echo "    cp -r \"$APP\" /Applications/"
    echo ""

    # Optional: open the dist folder in Finder
    read -p "  Open dist/ folder in Finder? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        open dist/
    fi
else
    echo ""
    echo "  ✗  Build failed — check errors above."
    exit 1
fi

echo "══════════════════════════════════════════"
echo ""
