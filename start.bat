@echo off
title NEXUS Single-Command Startup
echo ==============================================
echo   NEXUS Global News Intelligence Launcher
echo ==============================================
echo.
powershell -ExecutionPolicy Bypass -Command "& { if (Test-Path 'start.py') { python start.py } else { Write-Host 'Error: start.py not found in current directory.' -ForegroundColor Red } }"
pause
