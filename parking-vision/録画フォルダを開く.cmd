@echo off
chcp 65001 >nul
set "RECORDINGS=%LOCALAPPDATA%\ParkingResearch\Recordings"
if not exist "%RECORDINGS%" (
  echo まだ録画がありません。先に「ホーム駐車場_かんたん準備.cmd」でカメラ判定を開始してください。
  pause
  exit /b 1
)
start "" "%RECORDINGS%"
