# 現地で人が空車を確認した区画だけ短時間承認する。未確認区画は空車にしない。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$configFile = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
  throw "config.json がありません。先にホーム駐車場の設定を行ってください。"
}
$pythonCandidates = @(
  (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Desktop\parking-yolo-starter\.venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\.venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
  Select-Object -First 1
if (-not $python) { throw "研究用Pythonが見つかりません。先にライブ実験の環境を確認してください。" }
Write-Host "YOLO共有が動いている場合は、先に q キーで終了してください。"
& $python (Join-Path $PSScriptRoot "confirm_initial_empty.py") --config $configFile
if ($LASTEXITCODE -ne 0) { throw "現地空車確認の設定を完了できませんでした。" }
