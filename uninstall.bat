@echo off
title ChronoRecovery - Uninstaller
echo ============================================================
echo   ChronoRecovery: Uninstalling Application
echo ============================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action Uninstall
echo.
pause
