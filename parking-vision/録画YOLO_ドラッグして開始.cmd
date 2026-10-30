@echo off
cd /d "%~dp0"
rem Same text menu as the original demo. Japanese UI lives in BOM-encoded PowerShell.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_video_demo_menu.ps1"
