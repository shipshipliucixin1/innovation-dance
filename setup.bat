@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
  echo Setup failed. Other environments were not used as installation targets.
  pause
  exit /b 1
)
echo Ready. Run start.bat to open ProjectFlow.
pause
endlocal
