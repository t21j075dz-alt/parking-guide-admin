param(
    [Parameter(Mandatory=$true)][string]$SourceConfig,
    [Parameter(Mandatory=$true)][string]$Video
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
Write-Host ""
Write-Host "========== 駐車区画の取り込み =========="
Write-Host "録画動画と既存6区画を重ねて表示します。"
Write-Host "完全に一致する場合は映像画面でS、ずれる場合はQを押してください。"
try {
    if (-not $python) { throw "YOLO用Pythonが見つかりません。" }
    $argsForPython = @(
        (Join-Path $PSScriptRoot "reuse_live_zones_for_video.py"),
        "--source-config", $SourceConfig,
        "--demo-config", (Join-Path $PSScriptRoot "config_video_demo.json"),
        "--video", $Video
    )
    & $python @argsForPython
    if ($LASTEXITCODE -ne 0) { throw "区画の取り込みに失敗しました。上のエラーをご確認ください。" }
} catch {
    Write-Host "【エラー】$($_.Exception.Message)" -ForegroundColor Red
} finally {
    Write-Host ""
    [void](Read-Host "Enterキーでこの画面を閉じます")
}
