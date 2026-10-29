@echo off
setlocal
cd /d "%~dp0"
if not exist ".conda-env\python.exe" (
  echo Project environment missing. Run setup.bat first. No global Python will be used.
  pause
  exit /b 1
)
".conda-env\python.exe" scripts\verify_env.py
if errorlevel 1 (
  pause
  exit /b 1
)
".conda-env\python.exe" -m projectflow.server
if errorlevel 1 pause
endlocal
