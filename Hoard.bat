@echo off
setlocal
cd /d "%~dp0"
title Hoard
if not exist ".venv\Scripts\python.exe" call Setup.bat --quiet || exit /b 1
rem Python can keep running old compiled copies of files updated over an old install: always start from the files.
set "PYTHONDONTWRITEBYTECODE=1"
if exist "hoard\__pycache__" rmdir /s /q "hoard\__pycache__"
if "%~1"=="" (
  rem The app: in its own window (or your browser), with no console left open.
  start "" ".venv\Scripts\pythonw.exe" -m hoard
) else (
  rem A command (Hoard.bat sync, Hoard.bat verify, ...): run here, so its output shows.
  ".venv\Scripts\python.exe" -m hoard %*
  if errorlevel 1 pause
)
