@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ===========================================
echo 駐車場マップと実カメラの位置合わせ確認
echo ===========================================
echo 現在のYOLOとカメラ配信を停止してから実行してください。
echo.
set "ALIGNMENT=%~1"
if not defined ALIGNMENT (
  echo 管理者アプリから保存した「camera-map-alignment-...json」の
  echo フルパスを貼り付けるか、ファイルをこの画面にドラッグしてください。
  set /p ALIGNMENT=位置合わせJSON:
)
set "ALIGNMENT=%ALIGNMENT:"=%"
if not exist "%ALIGNMENT%" (
  echo [中止] 指定された位置合わせJSONが見つかりません。
  pause
  exit /b 1
)
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not exist "config.json" (
  echo [中止] config.json が見つかりません。研究用PCで実行してください。
  pause
  exit /b 1
)
echo.
echo カメラが開いたら SPACE で静止し、6区画すべてを確認してください。
echo 合っていたら V を押して確認記録を保存します。
echo 取り消す場合は Q を押してください。
echo.
"%PYTHON%" ".\verify_map_alignment.py" --config ".\config.json" --alignment "%ALIGNMENT%"
if errorlevel 1 (
  echo [失敗] カメラ接続または区画の位置合わせを確認してください。
  pause
  exit /b 1
)
echo.
echo 実際のYOLO設定は変更していません。
echo 次は確認記録JSONを使って import_map_alignment.py で反映できます。
pause
