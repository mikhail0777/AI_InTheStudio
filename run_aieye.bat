@echo off
title AI(EYE) in the sky - Mission Control Launcher
color 0A

echo ======================================================================
echo           AI(EYE) in the sky - SAR Drone Analysis Platform
echo ======================================================================
echo.

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: Add Node.js to PATH if present
if exist "C:\Program Files\nodejs" set "PATH=C:\Program Files\nodejs;%PATH%"

:: Select Python interpreter
set "PYTHON_EXE="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
)
if "%PYTHON_EXE%"=="" (
    set "PYTHON_EXE=python"
)

:: Select npm command
set "NPM_CMD=npm"
if exist "C:\Program Files\nodejs\npm.cmd" (
    set "NPM_CMD=C:\Program Files\nodejs\npm.cmd"
)

echo Starting Backend API server on port 8000...
start "AI(EYE) Backend" cmd /k "cd /d "%ROOT_DIR%\backend" && "%PYTHON_EXE%" -m app.main"

echo Waiting for backend initialization...
ping -n 4 127.0.0.1 >nul

echo Starting Frontend UI on port 5173...
start "AI(EYE) Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && "%NPM_CMD%" run dev"

echo Waiting for frontend initialization...
ping -n 3 127.0.0.1 >nul

echo Launching browser...
start http://localhost:5173

echo.
echo ======================================================================
echo [OK] AI(EYE) in the sky is running!
echo.
echo  - Web UI:       http://localhost:5173
echo  - Backend Docs: http://localhost:8000/docs
echo ======================================================================
echo.
pause
