@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo =========================================================
echo 道の駅日光 - 駐車枠なしでYOLOの認識だけを確認する
echo =========================================================
echo 駐車枠や空き判定なし／Supabase送信なし
echo 元動画 G:\parking-movie を利用（原本は変更しません）
echo.
echo 1. 1周だけ検出結果を見る（最初の確認におすすめ）
echo 2. 同じ動画をループして検出結果を見る
echo 3. 1周を全フレームで判定して結果MP4も保存
echo 4. 1周を全フレームで判定して見る（保存なし）
echo.
set /p MODE=番号を入力してください [1/2/3/4]:
set "MODEARG="
if "%MODE%"=="2" set "MODEARG=-Loop"
if "%MODE%"=="3" set "MODEARG=-SaveVideo -AllFrames"
if "%MODE%"=="4" set "MODEARG=-AllFrames"
if not "%MODE%"=="1" if not "%MODE%"=="2" if not "%MODE%"=="3" if not "%MODE%"=="4" (
  echo [中止] 1～4の番号を選んでください。
  pause
  exit /b 1
)
set "VIDEO=%~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nikko_detection_only.ps1" -Video "%VIDEO%" %MODEARG%
if errorlevel 1 (
  echo.
  echo [失敗] 上に表示された動画・モデル・Pythonのエラー内容を確認してください。
) else (
  echo.
  echo [完了] 検知結果の確認を終了しました。
)
echo.
pause
