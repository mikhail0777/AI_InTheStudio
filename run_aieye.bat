@echo off
setlocal EnableExtensions DisableDelayedExpansion
title AI(EYE) in the sky - Mission Control Launcher
color 0A

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "CHECK_ONLY=0"
set "OPEN_BROWSER=1"

if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"
if not "%~1"=="" if /I not "%~1"=="--check" if /I not "%~1"=="--no-browser" goto usage
if not "%~2"=="" goto usage

echo ======================================================================
echo           AI(EYE) in the sky - Local Development Launcher
echo ======================================================================
echo.

if exist "C:\Program Files\nodejs" set "PATH=C:\Program Files\nodejs;%PATH%"

set "PYTHON_EXE="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
    where python.exe >nul 2>&1
    if errorlevel 1 goto missing_python
    set "PYTHON_EXE=python.exe"
)

echo Running startup checks...
"%PYTHON_EXE%" "%ROOT_DIR%\scripts\launcher_check.py" preflight
if errorlevel 1 goto preflight_failed

if "%CHECK_ONLY%"=="1" (
    echo.
    echo [OK] Startup checks passed. No services were started.
    exit /b 0
)

"%PYTHON_EXE%" "%ROOT_DIR%\scripts\launcher_check.py" port-free 127.0.0.1 8000
if errorlevel 1 goto backend_port_busy
"%PYTHON_EXE%" "%ROOT_DIR%\scripts\launcher_check.py" port-free 127.0.0.1 5173
if errorlevel 1 goto frontend_port_busy

echo.
echo Starting Backend API server on port 8000...
start "AI(EYE) Backend" /D "%ROOT_DIR%\backend" cmd.exe /k ""%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
if errorlevel 1 goto backend_launch_failed

echo Waiting for the Backend API health check...
"%PYTHON_EXE%" "%ROOT_DIR%\scripts\launcher_check.py" wait-url http://127.0.0.1:8000/ 45
if errorlevel 1 goto backend_health_failed

echo Starting Frontend UI on port 5173...
start "AI(EYE) Frontend" /D "%ROOT_DIR%\frontend" cmd.exe /k "npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort"
if errorlevel 1 goto frontend_launch_failed

echo Waiting for the Frontend UI health check...
"%PYTHON_EXE%" "%ROOT_DIR%\scripts\launcher_check.py" wait-url http://127.0.0.1:5173/ 45
if errorlevel 1 goto frontend_health_failed

if "%OPEN_BROWSER%"=="1" (
    echo Launching browser...
    start "" "http://127.0.0.1:5173"
)

echo.
echo ======================================================================
echo [OK] AI(EYE) in the sky is ready.
echo.
echo  - Web UI:       http://127.0.0.1:5173
echo  - Backend Docs: http://127.0.0.1:8000/docs
echo ======================================================================
echo.
pause
exit /b 0

:usage
echo Usage: %~nx0 [--check ^| --no-browser]
echo   --check       Validate prerequisites without starting services.
echo   --no-browser  Start both services without opening a browser.
exit /b 2

:missing_python
echo [ERROR] Python was not found. Install Python 3.10+ or create .venv in the repository root.
goto failed

:preflight_failed
echo [ERROR] Startup checks failed. Follow the message above, then run this launcher again.
goto failed

:backend_port_busy
echo [ERROR] Port 8000 is already in use. Stop the existing process or service first.
goto failed

:frontend_port_busy
echo [ERROR] Port 5173 is already in use. Stop the existing process or service first.
goto failed

:backend_launch_failed
echo [ERROR] Windows could not open the Backend process.
goto failed

:backend_health_failed
echo [ERROR] The Backend did not become healthy within 45 seconds. Review the Backend window.
goto failed

:frontend_launch_failed
echo [ERROR] Windows could not open the Frontend process.
goto failed

:frontend_health_failed
echo [ERROR] The Frontend did not become healthy within 45 seconds. Review the Frontend window.
goto failed

:failed
echo.
if "%CHECK_ONLY%"=="1" exit /b 1
pause
exit /b 1
