# デスクトップ専用：録画動画→YOLO判定→（明示許可時のみ）録画実演用の案内
param(
  [string]$Video = "",
  [switch]$Share,
  [string]$VerifiedEmpty = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonCandidates = @(
  (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\.venv\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    & $candidate -c "import cv2, ultralytics" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
  }
}
if (-not $python) { throw "YOLO用Pythonが見つかりません。研究用の環境をご確認ください。" }
Write-Host ""
Write-Host "========== 録画動画 → YOLO → 駐車場案内 =========="
Write-Host "【研究用Python】$python"
Write-Host "【重要】録画再生による実演です。実際の現在の空き情報ではありません。"
Write-Host "【安全】自宅実カメラ施設のデータは変更せず、録画専用施設に分離します。"

$demoConfig = Join-Path $PSScriptRoot "config_video_demo.json"
if (-not (Test-Path -LiteralPath $demoConfig -PathType Leaf)) {
  $laptopConfig = Join-Path $PSScriptRoot "config_from_laptop.json"
  if (-not (Test-Path -LiteralPath $laptopConfig -PathType Leaf)) {
    $laptopConfig = Join-Path $PSScriptRoot "config_from_laptop_fixed.json"
  }
  if (-not (Test-Path -LiteralPath $laptopConfig -PathType Leaf)) {
    throw "ノートPCの6区画ファイル config_from_laptop.json が見つかりません。"
  }
  & $python (Join-Path $PSScriptRoot "prepare_video_demo.py") --desktop "config.json" --laptop $laptopConfig --output $demoConfig
  if ($LASTEXITCODE -ne 0) { throw "録画実演の設定作成に失敗しました。" }
}

if ([string]::IsNullOrWhiteSpace($Video)) {
  $Video = Read-Host "再生するMP4等の動画をフルパスで入力（ファイルのドラッグも可）"
}
$Video = $Video.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Video -PathType Leaf)) {
  throw "録画ファイルがありません: $Video"
}

$videoSettings = Get-Content -LiteralPath $demoConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Test-Path -LiteralPath ([string]$videoSettings.vehicle_model) -PathType Leaf)) {
  throw "学習モデルが見つかりません。config_video_demo.json のvehicle_modelを確認してください。"
}
Write-Host "【映像】$Video"
Write-Host "【AIモデル】$($videoSettings.vehicle_model)"
$flags = @("--config", $demoConfig, "--video", $Video, "--preview")
if (-not [string]::IsNullOrWhiteSpace($VerifiedEmpty)) {
  $flags += @("--verified-empty", $VerifiedEmpty)
}
if ($Share) {
  Write-Host "【案内共有】録画実演専用の施設（home-video-demo-001）へ共有します。"
  $approve = Read-Host "共有する場合だけ「録画共有」と入力"
  if ($approve -ne "録画共有") {
    Write-Host "【中止】共有されませんでした。"
    exit 0
  }
  $flags += "--demo-publish"
} else {
  Write-Host "【確認モード】クラウド送信なし。判定画面・CSV・動画のみ生成します。"
  $flags += "--dry-run"
}
& $python (Join-Path $PSScriptRoot "monitor.py") @flags
if ($LASTEXITCODE -ne 0) {
  throw "録画YOLOの解析に失敗しました。上の説明をご確認ください。"
}
Write-Host "【完了】録画動画の実演を終了しました。"
