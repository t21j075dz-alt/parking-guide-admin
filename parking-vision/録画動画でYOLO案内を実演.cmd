@echo off
chcp 65001 >nul
echo ================================================
echo 録画動画をYOLOで判定し、案内へ反映する研究実演
echo ================================================
echo.
echo 1. デスクトップPC内だけで確認（クラウド送信しない）
echo 2. 録画実演専用のユーザーアプリへ共有
echo.
set /p choice=番号を選択してください（1/2）:
if "%choice%"=="2" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_video_demo.ps1" -Share
) else if "%choice%"=="1" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_video_demo.ps1"
) else (
  echo 番号が正しくありません。
)
pause
