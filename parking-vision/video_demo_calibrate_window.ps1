param([Parameter(Mandatory=$true)][string]$Video)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
Write-Host "========== 録画動画の区画を新規登録 =========="
Write-Host "旧カメラと画角が異なる場合はこちらを使用してください。"
Write-Host "動画から6区画の4隅を指定します。Qで保存、Escで中止。"
try {
    if (-not $python) { throw "YOLO用Pythonが見つかりません。" }
    $argsForPython = @(
        (Join-Path $PSScriptRoot "calibrate.py"),
        "--config", (Join-Path $PSScriptRoot "config_video_demo.json"),
        "--source", $Video
    )
    & $python @argsForPython
    if ($LASTEXITCODE -ne 0) { throw "区画の登録に失敗しました。上のエラーを確認してください。" }
} catch {
    Write-Host "【エラー】$($_.Exception.Message)" -ForegroundColor Red
} finally {
    [void](Read-Host "Enterキーでこのウィンドウを閉じます")
}
