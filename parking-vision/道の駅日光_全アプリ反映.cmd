@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo =====================================================
echo 道の駅日光：位置合わせJSONを全アプリへ反映
echo =====================================================
echo [注意] 過去の録画を繰り返す研究用デモです。
echo [手順] 位置合わせJSONの選択 → 動画3場面確認 → YOLOループ
echo [共有] 録画共有と写真共有は別々に確認されます。
echo.
set "ALIGNMENT="
set "VIDEO="
if /I "%~x1"==".json" (
  set "ALIGNMENT=%~1"
  set "VIDEO=%~2"
) else (
  set "VIDEO=%~1"
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nikko_all_apps.ps1" -Alignment "%ALIGNMENT%" -Video "%VIDEO%"
if errorlevel 1 (
  echo.
  echo [エラー] 上の内容と位置合わせJSONを確認してください。
) else (
  echo.
  echo [終了] 動画共有が停止しました。
)
echo.
pause
