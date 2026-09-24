@echo off
setlocal
cd /d "%~dp0"
title Hoard
if not exist ".venv\Scripts\python.exe" call Setup.bat --quiet || exit /b 1
rem Hoard opens in your browser. Keep this window open while you use it; close it to quit Hoard.
".venv\Scripts\python.exe" -m hoard %*
if errorlevel 1 pause
