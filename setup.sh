#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     ØJE CUE MONITOR  v0.97beta       ║"
echo "║     Setup for macOS                  ║"
echo "║     © 2026 ØJE Studio               ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Homebrew check ────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo "ERROR: Homebrew not found."
    echo "Install from:  https://brew.sh"
    exit 1
fi

# ── System dependencies ───────────────────────────────────────────────────────
echo "▶  Installing portaudio  (required by pyaudio)..."
brew install portaudio

echo ""
echo "▶  Installing libltc  (LTC decoder)..."
brew install libltc

# ── Python dependencies ───────────────────────────────────────────────────────
echo ""
echo "▶  Installing Python packages..."
pip3 install -r requirements.txt

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""
echo "▶  Verifying libltc..."
python3 -c "
import ctypes, ctypes.util, os
paths = ['/opt/homebrew/lib/libltc.dylib', '/usr/local/lib/libltc.dylib']
found = next((p for p in paths if os.path.exists(p)), ctypes.util.find_library('ltc'))
if found:
    print('   libltc :', found, '  ✓')
else:
    print('   WARNING: libltc not found — LTC decoding will not work')
"

echo ""
echo "▶  Verifying pyaudio..."
python3 -c "
import pyaudio
pa = pyaudio.PyAudio()
count = pa.get_device_count()
pa.terminate()
print(f'   pyaudio : OK — {count} audio device(s) found  ✓')
"

echo ""
echo "▶  Verifying PyQt6..."
python3 -c "from PyQt6.QtWidgets import QApplication; print('   PyQt6   : OK  ✓')"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Setup complete."
echo ""
echo "  Launch:  python3 main.py"
echo ""
echo "  NOTE: On first run macOS will request"
echo "  microphone permission — allow it in:"
echo "  System Settings › Privacy › Microphone"
echo "══════════════════════════════════════════"
echo ""
