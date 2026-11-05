@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ===================================================
echo 道の駅日光 - 録画動画をYOLOで逐次判定
echo ===================================================
echo 1. PCだけで再生・判定する（安全な初期設定）
echo 2. 利用者アプリへ録画の判定結果を共有する
echo 3. 全フレーム解析を行う（取りこぼし防止・速度低下あり）
echo.
set /p MODE=番号を選んでください [1/2/3]:
if "%MODE%"=="1" set "MODEARG="
if "%MODE%"=="2" set "MODEARG=-Share"
if "%MODE%"=="3" set "MODEARG=-AllFrames"
if not "%MODE%"=="1" if not "%MODE%"=="2" if not "%MODE%"=="3" (
  echo [中止] 1～3から選んでください。
  pause
  exit /b 1
)
set "VIDEO=%~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nikko_video.ps1" -Video "%VIDEO%" %MODEARG%
if errorlevel 1 (
  echo.
  echo [エラー] 表示された内容を確認してください。
)
echo.
pause
