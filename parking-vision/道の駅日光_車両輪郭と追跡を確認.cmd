@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ========================================================
echo Nikko - YOLO vehicle contours / masks / stable track IDs
echo ========================================================
echo No parking zones. No Supabase network or database changes.
echo Locally trained YOLO segmentation model will be selected.
echo.
echo 1. High 960px, preview one playback  [recommended]
echo 2. High 960px, loop playback
echo 3. Maximum 1280px, preview one playback
echo 4. High 960px, ALL frames and save annotated MP4
echo.
set /p MODE=Select mode [1/2/3/4]:
set "MODEARG="
if "%MODE%"=="2" set "MODEARG=-Loop"
if "%MODE%"=="3" set "MODEARG=-Quality Maximum"
if "%MODE%"=="4" set "MODEARG=-SaveVideo -AllFrames"
if not "%MODE%"=="1" if not "%MODE%"=="2" if not "%MODE%"=="3" if not "%MODE%"=="4" (
  echo Invalid choice. Select 1 through 4.
  pause
  exit /b 1
)
set "VIDEO=%~1"
set "SEGMODEL=%~2"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nikko_segmentation.ps1" -Video "%VIDEO%" -SegmentationModel "%SEGMODEL%" %MODEARG%
if errorlevel 1 (
  echo.
  echo ERROR: Check the Python / video / model error above.
) else (
  echo.
  echo FINISHED: vehicle-segmentation preview ended.
)
echo.
pause
