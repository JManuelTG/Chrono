@echo off
title ChronoRecovery - Installation
echo ============================================================
echo   ChronoRecovery: Installing Dependencies
echo ============================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [*] Installing required packages from requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation encountered an error.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [OK] ChronoRecovery dependencies successfully installed!
echo ============================================================
echo.
set /p run_inst="Would you like to run the Windows Desktop Installer now? [Y/n]: "
if /i "%run_inst%"=="n" (
    echo.
    echo To launch the application, run 'run_gui.bat' or 'python recovery_gui.py'.
    pause
    exit /b 0
)

call "%~dp0installer.bat" install
pause
