@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ========================================================
echo 道の駅日光 - 車両輪郭 / マスク / 安定IDを確認
echo ========================================================
echo [非公開] 駐車枠なし・Supabaseには一切送信しません。
echo [モデル] 自宅PCの追加学習済み-segモデルを検索します。
echo.
echo 1. High 960px で1周だけプレビュー（おすすめ）
echo 2. High 960px でループ再生
echo 3. Maximum 1280px で1周だけプレビュー
echo 4. High 960px で全フレームを判定しMP4保存
echo.
set /p MODE=番号を入力してください [1/2/3/4]:
set "MODEARG="
if "%MODE%"=="2" set "MODEARG=-Loop"
if "%MODE%"=="3" set "MODEARG=-Quality Maximum"
if "%MODE%"=="4" set "MODEARG=-SaveVideo -AllFrames"
if not "%MODE%"=="1" if not "%MODE%"=="2" if not "%MODE%"=="3" if not "%MODE%"=="4" (
  echo [中止] 番号1から4を入力してください。
  pause
  exit /b 1
)
set "VIDEO=%~1"
set "SEGMODEL=%~2"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nikko_segmentation.ps1" -Video "%VIDEO%" -SegmentationModel "%SEGMODEL%" %MODEARG%
if errorlevel 1 (
  echo.
  echo [エラー] 上のモデル名・動画・Pythonの状態を確認してください。
) else (
  echo.
  echo [完了] 車両輪郭の確認を終了しました。
)
echo.
pause
