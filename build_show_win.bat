@echo off
chcp 65001 >nul 2>&1
echo.
echo ╔══════════════════════════════════════════╗
echo ║   OJE SHOW MONITOR  —  Build            ║
echo ║   Windows x64  .exe                      ║
echo ╚══════════════════════════════════════════╝
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.9+ from python.org
    pause
    exit /b 1
)

echo ▶  Installing dependencies...
pip install pyinstaller pyqt6 numpy
if errorlevel 1 (
    echo.
    echo ERROR: Dependency install failed.
    pause
    exit /b 1
)

echo ▶  Cleaning previous SHOW MONITOR build...
if exist "build\OJEShowMonitor" rmdir /s /q "build\OJEShowMonitor"
if exist "dist\OJE SHOW MONITOR.exe" del /q "dist\OJE SHOW MONITOR.exe"

echo.
echo ▶  Building .exe...
python -m PyInstaller OJEShowMonitor_win.spec --noconfirm

if exist "dist\OJE SHOW MONITOR.exe" (
    echo.
    echo ══════════════════════════════════════════
    echo   ✓  Build successful!
    echo.
    echo   File: dist\OJE SHOW MONITOR.exe
    echo ══════════════════════════════════════════
) else (
    echo.
    echo   ✗  Build failed — check errors above.
)
echo.
pause
