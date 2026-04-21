@echo off
chcp 65001 >nul 2>&1
echo.
echo ╔══════════════════════════════════════╗
echo ║   OJE CUE MONITOR  —  Build         ║
echo ���   Windows x64  .exe                  ║
echo ╚══════════════════════════════════════╝
echo.

:: ── Check Python ────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9+ from python.org
    pause
    exit /b 1
)

:: ── Check libltc.dll ────────────────────────────────────────────────────────
if not exist "libs\win64\libltc.dll" (
    echo ERROR: libs\win64\libltc.dll not found.
    echo        This file should be included in the repository.
    pause
    exit /b 1
)

:: ── Install dependencies ────────────────────────────────────────────────────
:: qrcode[pil] pulls in Pillow — required for PNG QR rendering in web_remote.py.
:: Errors are left visible so missing wheels (e.g. pyaudio) are obvious.
echo ▶  Installing dependencies...
pip install pyinstaller pyqt6 pyaudio numpy "qrcode[pil]" aiohttp Pillow
if errorlevel 1 (
    echo.
    echo ERROR: Dependency install failed. If pyaudio is the problem, try:
    echo   pip install pipwin
    echo   pipwin install pyaudio
    echo.
    pause
    exit /b 1
)

:: ── Clean previous build ────────────────────────────────────────────────────
echo ▶  Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

:: ── Build ───────────────────────────────────────────────────────────────────
echo.
echo ▶  Building .exe...
python -m PyInstaller OJECueMonitor_win.spec --noconfirm

:: ── Result ──────────────────────────────────────────────────────────────────
if exist "dist\OJE CUE MONITOR.exe" (
    echo.
    echo ══════════════════════════════════════════
    echo   ✓  Build successful!
    echo.
    echo   File: dist\OJE CUE MONITOR.exe
    echo.
    echo   Double-click the .exe to run.
    echo ══════════════════════════════════════════
) else (
    echo.
    echo   ✗  Build failed — check errors above.
)
echo.
pause
