@echo off
title Crypto Trading Bot
echo.
echo ========================================
echo   Crypto Trading Bot - Starting...
echo ========================================
echo.

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [!] Virtual environment not found.
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo [ERROR] Make sure Python 3.11+ is installed and in PATH.
        pause
        exit /b 1
    )
    
    echo [*] Installing Python dependencies...
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
) else (
    call venv\Scripts\activate.bat
)

REM Check if electron node_modules exists
if not exist "electron\node_modules" (
    echo [*] Installing Electron dependencies...
    cd electron
    npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install Electron dependencies.
        echo [ERROR] Make sure Node.js 18+ is installed and in PATH.
        cd ..
        pause
        exit /b 1
    )
    cd ..
)

echo.
echo [*] Starting Crypto Trading Bot...
echo.
python start.py

if errorlevel 1 (
    echo.
    echo [ERROR] Bot exited with an error.
    pause
)
