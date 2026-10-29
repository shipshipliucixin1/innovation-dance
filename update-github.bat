@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update_github.ps1"
if errorlevel 1 (
  echo Update stopped. Read the message above. No force push was attempted.
  pause
  exit /b 1
)
pause
endlocal
