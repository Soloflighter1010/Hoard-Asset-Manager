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
echo   2  Sign out of a store
echo   3  Preview what would download
echo   4  Download everything new
echo   5  Browse your downloads
echo   6  Open config.json
echo   7  Quit
echo.
set "choice="
set /p "choice=Choose 1-7: "
if "%choice%"=="1" goto signin
if "%choice%"=="2" goto signout
if "%choice%"=="3" %RUN% sync --dry-run
if "%choice%"=="4" %RUN% sync
if "%choice%"=="5" %RUN% browse
if "%choice%"=="6" start "" notepad "config.json"
if "%choice%"=="7" exit /b 0
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

:signout
echo.
echo   1  Booth
echo   2  Gumroad
echo   3  Jinxxy
echo   4  Payhip
echo   5  Every store (deletes all of Hoard's saved sign-ins)
echo   6  Back
echo.
set "store="
set /p "store=Sign out of which store? 1-6: "
if "%store%"=="1" %RUN% logout booth
if "%store%"=="2" %RUN% logout gumroad
if "%store%"=="3" %RUN% logout jinxxy
if "%store%"=="4" %RUN% logout payhip
if "%store%"=="5" %RUN% logout all
goto menu
