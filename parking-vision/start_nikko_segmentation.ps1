#requires -Version 5.1
# 道の駅日光：写真の駐車区画なしで追加学習済み車両輪郭モデルを可視化
param(
  [string]$Video = "",
  [string]$SegmentationModel = "",
  [ValidateSet("High","Maximum","Standard")]
  [string]$Quality = "High",
  [switch]$Loop,
  [switch]$SaveVideo,
  [switch]$AllFrames
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
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  & $candidate -c "import cv2, ultralytics" 2>$null
  if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (-not $python) { throw "YOLOの研究用Python環境が見つかりません。" }
Write-Host "【PC】既存GPU対応Python: $python"
Write-Host "【実験】駐車枠なし／車両輪郭と追跡ID／Supabase送信なし"
Write-Host "【品質】$Quality（High=960px、Maximum=1280px。性能は目視評価が必要）"
$videoRoot = "G:\parking-movie"
if (-not $Video) {
  $preferred = Join-Path $videoRoot "道の駅日光駐車場ライブカメラ_ニコニコ本陣_0533.mp4"
  if (Test-Path -LiteralPath $preferred -PathType Leaf) {
    $Video = $preferred
  } else {
    $videos = @(
      Get-ChildItem -LiteralPath $videoRoot -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".mp4",".avi",".mov",".mkv",".webm")
          -and $_.Name -notmatch '^(YOLO判定_|yolo_annotated)' } |
        Sort-Object Name
    )
    if ($videos.Count -eq 0) { throw "G:\parking-movieに元動画が見つかりません。" }
    for ($i=0; $i -lt $videos.Count; $i++) {
      Write-Host ("{0}. {1}" -f ($i+1), $videos[$i].Name)
    }
    $num = 0
    $answer = (Read-Host "道の駅日光の元動画の番号").Trim()
    if (-not [int]::TryParse($answer,[ref]$num) -or $num -lt 1 -or $num -gt $videos.Count) {
      throw "動画番号が正しくありません。"
    }
    $Video = $videos[$num-1].FullName
  }
}
$Video=([string]$Video).Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Video -PathType Leaf)) { throw "動画がありません: $Video" }
$Video=(Resolve-Path -LiteralPath $Video).Path
Write-Host "【動画】$Video"

# 以前のセグメンテーション学習と一般的なYOLO実験フォルダを検索。
# 更新日時は候補の並び順としてのみ使う（精度・学習の新しさの証拠とはしない）。
if (-not $SegmentationModel) {
  $searchFolders = @(
    (Join-Path $env:USERPROFILE "parking-yolo-home\runs"),
    (Join-Path $env:USERPROFILE "parking-vision\runs"),
    (Join-Path $env:USERPROFILE "parking-guide-admin\parking-vision\runs"),
    (Join-Path $env:USERPROFILE "Desktop\parking-yolo-starter\runs"),
    (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\runs")
  ) | Select-Object -Unique
  $candidates = @()
  foreach ($root in $searchFolders) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
    $candidates += @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -in @("last.pt","best.pt") -and
                     $_.DirectoryName -match '[\\/]weights$' })
  }
  $candidates = @($candidates | Sort-Object FullName -Unique |
    Sort-Object LastWriteTime -Descending)
  $segments = @()
  Write-Host "【学習重み】候補 $($candidates.Count)件。segmentモデルか検証します。"
  foreach ($item in $candidates) {
    if ($segments.Count -ge 6) { break }
    $task = @(& $python -c "from ultralytics import YOLO; import sys; print(YOLO(sys.argv[1]).task)" $item.FullName 2>$null)
    if ($LASTEXITCODE -eq 0 -and $task -contains "segment") {
      $segments += $item
    }
  }
  if ($segments.Count -gt 0) {
    Write-Host "【使える輪郭モデル】更新日時の新しい順"
    for ($i=0; $i -lt $segments.Count; $i++) {
      Write-Host ("{0}. {1}  {2}" -f ($i+1),
        $segments[$i].LastWriteTime.ToString("yyyy/MM/dd HH:mm"),
        $segments[$i].FullName)
    }
    $answer=(Read-Host "使用モデル番号（Enterで1番、0で別のパスを入力）").Trim()
    if (-not $answer) { $answer="1" }
    $num=0
    if (-not [int]::TryParse($answer,[ref]$num)) { throw "モデル番号が不正です。" }
    if ($num -ge 1 -and $num -le $segments.Count) {
      $SegmentationModel=$segments[$num-1].FullName
    } elseif ($num -ne 0) { throw "モデル番号が範囲外です。" }
  }
  if (-not $SegmentationModel) {
    Write-Host "【以前の追加学習候補】runs\unified_training\vehicle_lighting_auto_v1\weights\last.pt"
    $SegmentationModel = Read-Host "学習済み車体輪郭モデルの.ptファイルをフルパスで指定"
  }
}
$SegmentationModel=([string]$SegmentationModel).Trim().Trim('"')
if (-not (Test-Path -LiteralPath $SegmentationModel -PathType Leaf)) {
  throw "輪郭モデルが見つかりません: $SegmentationModel"
}
$SegmentationModel=(Resolve-Path -LiteralPath $SegmentationModel).Path
$task = @(& $python -c "from ultralytics import YOLO; import sys; print(YOLO(sys.argv[1]).task)" $SegmentationModel 2>$null)
if ($LASTEXITCODE -ne 0 -or $task -notcontains "segment") {
  throw "このモデルは車両輪郭抽出用ではありません（task=segmentが必要）。"
}
Write-Host "【採用モデル】$SegmentationModel"
Write-Host "【操作】Q終了／Space一時停止／S画像保存／R先頭に戻る"
$flags=@(
  (Join-Path $PSScriptRoot "preview_nikko_no_zones.py"),
  "--video",$Video,
  "--config",(Join-Path $PSScriptRoot "config.json"),
  "--segmentation-tracking",
  "--segmentation-model",$SegmentationModel,
  "--segmentation-quality",$Quality.ToLowerInvariant()
)
if ($Loop) { $flags += "--loop" }
if ($SaveVideo) { $flags += "--save-video" }
if ($AllFrames) { $flags += "--all-frames" }
& $python @flags
if ($LASTEXITCODE -ne 0) { throw "車両輪郭プレビューの実行に失敗しました。" }
Write-Host "【完了】モデルと検出した輪郭を確認してください。"
