@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0video_demo_drop.ps1"
if errorlevel 1 (
  echo.
  echo The drag-and-drop app could not start. Please check the error message.
  pause
)
