@echo off
title ChronoRecovery
start "" pythonw recovery_gui.py
if %errorlevel% neq 0 (
    python recovery_gui.py
)
