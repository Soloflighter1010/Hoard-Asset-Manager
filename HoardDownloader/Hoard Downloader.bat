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
echo   1  Sign in to a store
echo   2  Preview what would download
echo   3  Download everything new
echo   4  Browse your downloads
echo   5  Open config.json
echo   6  Quit
echo.
set "choice="
set /p "choice=Choose 1-6: "
if "%choice%"=="1" goto signin
if "%choice%"=="2" %RUN% sync --dry-run
if "%choice%"=="3" %RUN% sync
if "%choice%"=="4" %RUN% browse
if "%choice%"=="5" start "" notepad "config.json"
if "%choice%"=="6" exit /b 0
goto menu

:signin
echo.
echo   1  Booth
echo   2  Gumroad
echo   3  Jinxxy
echo   4  Payhip
echo   5  Back
echo.
set "store="
set /p "store=Sign in to which store? 1-5: "
if "%store%"=="1" %RUN% login booth
if "%store%"=="2" %RUN% login gumroad
if "%store%"=="3" %RUN% login jinxxy
if "%store%"=="4" %RUN% login payhip
goto menu
