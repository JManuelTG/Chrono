@echo off
setlocal EnableDelayedExpansion
title ChronoRecovery - Suite Installer

:: Check arguments for non-interactive execution
if /i "%1"=="install" goto do_install
if /i "%1"=="build" goto do_build
if /i "%1"=="uninstall" goto do_uninstall
if /i "%1"=="shortcuts" goto do_shortcuts
if /i "%1"=="associate" goto do_associate

:menu
cls
echo ===============================================================================
echo     ____ _                             ____                                   
echo    / ___^| ^|__  _ __ ___  _ __   ___   ^|  _ \ ___  ___ _____   _____ _ __ _   _ 
echo   ^| ^|   ^| '_ \^| '__/ _ \^| '_ \ / _ \  ^| ^|_) / _ \/ __/ _ \ \ / / _ \ '__^| ^| ^| ^|
echo   ^| ^|___^| ^| ^| ^| ^| ^| (_) ^| ^| ^| ^| (_) ^| ^|  _ ^<  __/ (_^| (_) \ V /  __/ ^|  ^| ^|_^| ^|
echo    \____^|_^| ^|_^|_^|  \___/^|_^| ^|_^|\___/  ^|_^| \_\___^|\___\___/ \_/ \___^|_^|   \__, ^|
echo                                                                          ^|___/ 
echo                   Deep Filesystem Inspector ^& Data Recovery Suite
echo ===============================================================================
echo.
echo   [1] Full Installation
echo       - Copies executables to Local Programs
echo       - Creates Desktop Shortcut (with Admin Elevation)
echo       - Creates Start Menu Shortcuts
echo       - Registers .rsf File Association (double-click to open scan files)
echo       - Adds 'chrono' and 'chrono-cli' to User PATH
echo.
echo   [2] Build / Recompile Standalone Executables (.exe via PyInstaller)
echo.
echo   [3] Create Desktop ^& Start Menu Shortcuts (In-Place / Portable)
echo.
echo   [4] Register .rsf File Association Only
echo.
echo   [5] Launch ChronoRecovery GUI Now
echo.
echo   [6] Launch chrono CLI Help
echo.
echo   [7] Uninstall ChronoRecovery
echo.
echo   [8] Exit
echo.
echo ===============================================================================
set /p choice="Select an option [1-8]: "

if "%choice%"=="1" goto do_install
if "%choice%"=="2" goto do_build
if "%choice%"=="3" goto do_shortcuts
if "%choice%"=="4" goto do_associate
if "%choice%"=="5" goto do_run_gui
if "%choice%"=="6" goto do_run_cli
if "%choice%"=="7" goto do_uninstall
if "%choice%"=="8" goto end
goto menu

:do_install
echo.
echo ===============================================================================
echo [*] Checking prerequisites and binaries...
echo ===============================================================================

if not exist "%~dp0dist\ChronoRecovery.exe" (
    echo [!] Standalone binary dist\ChronoRecovery.exe not found.
    echo [*] Compiling standalone executables now...
    python "%~dp0build_exe.py"
    if errorlevel 1 (
        echo [ERROR] Build failed. Please ensure Python 3.10+ and pip are installed.
        pause
        goto menu
    )
)

echo [*] Launching installer helper...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action Install -SourceDir "%~dp0."
echo.
pause
goto menu

:do_build
echo.
python "%~dp0build_exe.py"
echo.
pause
goto menu

:do_shortcuts
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action CreateShortcuts -SourceDir "%~dp0."
echo.
pause
goto menu

:do_associate
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action RegisterAssociation -SourceDir "%~dp0."
echo.
pause
goto menu

:do_run_gui
echo.
echo [*] Launching ChronoRecovery GUI...
if exist "%~dp0dist\ChronoRecovery.exe" (
    start "" "%~dp0dist\ChronoRecovery.exe"
) else (
    start "" pythonw "%~dp0recovery_gui.py"
)
goto menu

:do_run_cli
echo.
echo [*] Launching chrono CLI...
if exist "%~dp0dist\chrono.exe" (
    "%~dp0dist\chrono.exe" --help
) else (
    python "%~dp0chrono_cli.py" --help
)
echo.
pause
goto menu

:do_uninstall
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action Uninstall
echo.
pause
goto menu

:end
exit /b 0
