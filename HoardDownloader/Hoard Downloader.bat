@echo off
setlocal
cd /d "%~dp0"
title Hoard Downloader
if not exist ".venv\Scripts\python.exe" call "%~dp0Setup.bat" --quiet || exit /b 1
set "RUN=.venv\Scripts\python.exe asset_dl.py"

rem Arguments go straight to the tool, for example:  "Hoard Downloader.bat" sync --dry-run
if not "%~1"=="" (
  %RUN% %*
  exit /b
)

:menu
echo.
echo  Hoard Downloader
echo  ----------------
echo   1  Sign in to Gumroad
echo   2  Sign in to Jinxxy
echo   3  Preview what would download
echo   4  Download everything new
echo   5  Browse your library
echo   6  Open config.json
echo   7  Quit
echo.
set "choice="
set /p "choice=Choose 1-7: "
if "%choice%"=="1" %RUN% login gumroad
if "%choice%"=="2" %RUN% login jinxxy
if "%choice%"=="3" %RUN% sync --dry-run
if "%choice%"=="4" %RUN% sync
if "%choice%"=="5" %RUN% browse
if "%choice%"=="6" start "" notepad "config.json"
if "%choice%"=="7" exit /b 0
goto menu
