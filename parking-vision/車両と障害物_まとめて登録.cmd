@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
set "PYTHON=%USERPROFILE%\parking-yolo-home\.venv-gpu\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%.venv-cpu\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Research Python not found. Check your installed virtual environment.
  pause
  exit /b 1
)
cd /d "%ROOT%"
"%PYTHON%" "%ROOT%unified_annotator.py" --workspace "%ROOT%annotation_workspaces\photos_242"
if errorlevel 1 (
  echo The annotation tool exited with an error. Review the message above.
  pause
  exit /b 1
)
exit /b 0
