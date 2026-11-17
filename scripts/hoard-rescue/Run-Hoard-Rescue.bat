@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" hoard_rescue.py --apply %*
) else (
  py -3 hoard_rescue.py --apply %*
)
pause
