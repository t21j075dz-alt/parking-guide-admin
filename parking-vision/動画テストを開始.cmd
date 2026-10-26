@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ----------------------------------------------
echo  駐車場AI：録画テストを開始
echo  ※この処理でクラウドへは公開しません。
echo ----------------------------------------------
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Mode video
echo.
pause
