@echo off
chcp 65001 >nul 2>&1
echo.
echo ╔══════════════════════════════════════╗
echo ║   OJE CUE MONITOR  v0.97beta        ║
echo ║   Setup for Windows x64             ║
echo ║   © 2026 OJE Studio                 ║
echo ╚══════════════════════════════════════╝
echo.

:: ── Check Python ────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo        Install Python 3.9+ from https://python.org
    echo        Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo ▶  Python: OK

:: ── Install pip packages ────────────────────────────────────────────────────
echo ▶  Installing Python packages...
pip install PyQt6 pyaudio numpy qrcode aiohttp

if errorlevel 1 (
    echo.
    echo NOTE: If pyaudio fails, try:
    echo   pip install pipwin
    echo   pipwin install pyaudio
    echo.
)

echo.
echo ══════════════════════════════════════════
echo   ✓  Setup complete!
echo.
echo   Run with:   python main.py
echo   Build exe:  build_win.bat
echo ══════════════════════════════════════════
echo.
pause
