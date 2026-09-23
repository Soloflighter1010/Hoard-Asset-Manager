@echo off
setlocal
cd /d "%~dp0"
title Hoard
if not exist ".venv\Scripts\python.exe" call "%~dp0Setup.bat" --quiet || exit /b 1
rem Opens the library in your browser. Keep this window open while you use it.
".venv\Scripts\python.exe" library.py %*
if errorlevel 1 pause
