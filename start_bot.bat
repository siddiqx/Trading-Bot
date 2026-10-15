@echo off
title Forex Trading Bot - Autonomous Telegram Supervisor
cd /d "%~dp0"

echo ==============================================================
echo   Forex Trading Bot (@Columbina_raiden_bot) 24/7 Supervisor
echo ==============================================================
echo.

if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Starting Bot Runner with %PYTHON_EXE%...
"%PYTHON_EXE%" scripts\run_telegram_bot.py

pause
