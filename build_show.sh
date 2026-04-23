#!/bin/bash
# Run with:  bash build_show.sh   or   ./build_show.sh
# Builds the SHOW MONITOR .app (does not touch the CUE MONITOR build).
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ØJE SHOW MONITOR  —  Build            ║"
echo "║   macOS  .app  bundle                    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "▶  Installing PyInstaller..."
    pip3 install pyinstaller
fi

echo "▶  Cleaning previous SHOW MONITOR build..."
rm -rf build/OJEShowMonitor dist/OJEShowMonitor "dist/ØJE SHOW MONITOR.app"

echo ""
echo "▶  Building .app bundle..."
python3 -m PyInstaller OJEShowMonitor.spec --noconfirm

APP="dist/ØJE SHOW MONITOR.app"

if [ -d "$APP" ]; then
    SIZE=$(du -sh "$APP" | cut -f1)
    echo ""
    echo "══════════════════════════════════════════"
    echo "  ✓  Build successful!"
    echo ""
    echo "  App : $APP"
    echo "  Size: $SIZE"
    echo ""
    echo "  To open:   open \"$APP\""
    echo "══════════════════════════════════════════"
else
    echo ""
    echo "  ✗  Build failed — check errors above."
    exit 1
fi
