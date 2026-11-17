@echo off
setlocal
cd /d "%~dp0"
if defined HOARD_RESCUE_PYTHON (
  "%HOARD_RESCUE_PYTHON%" -c "import sys,sqlite3; sys.exit(sys.version_info < (3,10))" >nul 2>&1
  if not errorlevel 1 goto custom
)
for %%P in (".venv\Scripts\python.exe" "venv\Scripts\python.exe" "..\..\.venv\Scripts\python.exe" "..\..\venv\Scripts\python.exe") do (
  if exist "%%~P" (
    "%%~P" -c "import sys,sqlite3; sys.exit(sys.version_info < (3,10))" >nul 2>&1
    if not errorlevel 1 (
      "%%~P" "%~dp0hoard_rescue.py"  %*
      goto done
    )
  )
)
python -c "import sys,sqlite3; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
  python "%~dp0hoard_rescue.py"  %*
  goto done
)
py -3 -c "import sys,sqlite3; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0hoard_rescue.py"  %*
  goto done
)
echo No working Python 3.10+ with SQLite was found. No rescue changes were made.
echo Copy these rescue files into your original Hoard checkout to use its .venv.
echo Or set HOARD_RESCUE_PYTHON to the full path of your Python executable.
echo If Python is not installed, install Python 3.10 or newer from python.org.
goto done
:custom
"%HOARD_RESCUE_PYTHON%" "%~dp0hoard_rescue.py"  %*
:done
pause
endlocal
