@echo off
setlocal enabledelayedexpansion

:: Navigate to script directory reliably using relative path
cd /d "%~dp0"

:: Detect Python Windowed Launcher (pyw / pythonw for pure GUI without console window)
set "PYTHON_CMD="
set "USE_START=0"

where pyw >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=pyw -3"
    set "USE_START=1"
) else (
    where pythonw >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=pythonw"
        set "USE_START=1"
    ) else (
        where py >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=py -3"
        ) else (
            where python >nul 2>nul
            if %errorlevel% equ 0 (
                set "PYTHON_CMD=python"
            )
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo ============================================================
    echo [ERROR] Python was not found on your computer.
    echo Please install Python 3.10 or newer from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo ============================================================
    echo.
    pause
    exit /b 1
)

:: Launch Daily GitHub Agent GUI
if "%USE_START%"=="1" (
    start "" %PYTHON_CMD% agent.py %*
    exit /b 0
) else (
    %PYTHON_CMD% agent.py %*
    exit /b %errorlevel%
)
