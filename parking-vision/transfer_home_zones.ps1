# デスクトップPCで映像に重ねて6区画が一致する場合だけ、旧PCの登録座標を引き継ぐ。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$configFile = Join-Path $PSScriptRoot "config.json"
$backupFile = Join-Path $PSScriptRoot "config_backup_desktop_before_camera.json"
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
  throw "【準備不足】先にデスクトップPCの外付けカメラを設定してください。"
}
$pythonCandidates = @(
  (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Desktop\parking-yolo-starter\.venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\.venv\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    & $candidate -c "import cv2, numpy, ultralytics" 2>$null
    if ($LASTEXITCODE -eq 0) {
      $python = $candidate
      break
    }
  }
}
if (-not $python) {
  throw "YOLO環境が見つかりません。start.ps1 と同じPythonを確認してください。"
}
Write-Host ""
Write-Host "========== ノートPCの駐車区画をデスクトップへ =========="
Write-Host "【Python】$python"
Write-Host "【安全】カメラ番号・モデルパス・Supabase接続先はデスクトップの設定を維持します。"
Write-Host "【安全】旧PCの空き確認状態はコピーしません。"
Write-Host "【検索】6区画が残ったバックアップを自動で確認します。"
Write-Host "【重要】バックアップが1区画だけなら、以前のノートPCのconfig.jsonが必要です。"
& $python (Join-Path $PSScriptRoot "transfer_home_zones.py") --config $configFile
if ($LASTEXITCODE -ne 0) {
  throw "引き継ぎを完了できませんでした。区画を保存していない場合は変更ありません。"
}
