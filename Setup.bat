@echo off
setlocal
cd /d "%~dp0"
title Hoard setup

rem Find Python 3.10 or newer
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 || goto :nopython

rem Only your account (plus Windows itself and administrators) may change this folder, so no other
rem account on this computer can swap in code that would then run with your store sign-ins.
set "ME="
for /f "delims=" %%u in ('whoami') do set "ME=%%u"
if defined ME icacls "%~dp0." /inheritance:r /grant:r "%ME%:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" /Q >nul 2>&1
if errorlevel 1 (
  echo Note: couldn't limit who can change this folder ^(its drive may not support permissions^).
) else (
  echo Only your account can change the files in this folder now.
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment in this folder...
  %PY% -m venv .venv || goto :fail
)
echo Installing packages ^(each one checked against the hash recorded in requirements.txt^)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --require-hashes -r requirements.txt || goto :fail
rem Hoard uses Microsoft Edge for store sign-ins; its own Chromium is only a fallback if Edge is missing.
if not exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" if not exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
  echo Microsoft Edge wasn't found, so installing the browser Hoard uses instead...
  ".venv\Scripts\python.exe" -m playwright install chromium || goto :fail
)

echo.
echo Setup finished. Start Hoard with Hoard.bat.
if /i not "%~1"=="--quiet" pause
exit /b 0

:nopython
echo Python 3.10 or newer is needed.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo then run Setup.bat again.
pause
exit /b 1

:fail
echo.
echo Setup failed. The error is above.
pause
exit /b 1
