@echo off
chcp 65001 >nul
title Auto Trading Bot - BTC/USDT
cd /d "%~dp0"

echo.
echo  ================================================
echo   Bybit Auto Futures Bot
echo   EMA + Order Block + Fibonacci
echo  ================================================
echo.

if not exist ".env" (
    echo  [ERROR] .env file not found.
    echo  Copy .env.example to .env and enter your API keys.
    echo.
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed.
    pause
    exit /b 1
)

pip show pybit >nul 2>&1
if errorlevel 1 (
    echo  Installing dependencies...
    pip install -r requirements.txt
    echo.
)

echo  Starting bot... (close this window to stop)
echo.
python main.py

echo.
echo  Bot stopped.
pause