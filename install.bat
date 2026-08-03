@echo off
REM FlowCore — Windows Installer
REM Usage: install.bat

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   FlowCore v1.0.0 — Windows Installer          ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo [INFO] Python found.
python --version

REM Check pip
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip not found.
    pause
    exit /b 1
)

REM Create directories
if not exist data mkdir data
if not exist logs mkdir logs
if not exist backups mkdir backups
if not exist config mkdir config

echo [INFO] Directories created.

REM Install dependencies
echo [INFO] Installing dependencies...
python -m pip install --upgrade pip --quiet 2>nul
python -m pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║      Installation Complete!                     ║
echo ╠══════════════════════════════════════════════════╣
echo ║  FlowCore v1.0.0                                ║
echo ║  Status: CLI Ready                              ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo Test:     python flowcore.py version
echo Health:   python flowcore.py health
echo Doctor:   python flowcore.py doctor
echo.
pause
