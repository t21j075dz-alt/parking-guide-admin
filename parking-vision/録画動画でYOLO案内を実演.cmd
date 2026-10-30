@echo off
cd /d "%~dp0"
rem Japanese messages are emitted by a BOM-encoded PowerShell script.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_video_demo_menu.ps1"
