@echo off
title AI(EYE) in the sky - Mission Control Launcher
color 0A

echo ======================================================================
echo           🛸 AI(EYE) in the sky - SAR Drone Analysis Platform
echo ======================================================================
echo.
echo Starting Backend API (FastAPI) and Frontend UI (Vite + React)...
echo.

:: Start FastAPI Backend on port 8000
start "AI(EYE) in the sky Backend Server" cmd /k "cd /d %~dp0backend && python -m app.main"

:: Wait 3 seconds for backend server startup
timeout /t 3 /nobreak >nul

:: Start React Vite Frontend on port 5173
start "AI(EYE) in the sky Frontend UI" cmd /k "cd /d %~dp0\frontend && npm run dev"

:: Wait 2 seconds and open default web browser
timeout /t 2 /nobreak >nul
start http://localhost:5173

echo ======================================================================
echo [OK] AI(EYE) in the sky is now running!
echo.
echo  - Frontend Web UI:  http://localhost:5173
echo  - Backend API Docs: http://localhost:8000/docs
echo ======================================================================
echo.
pause
