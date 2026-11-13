# Windows PowerShell 5.1 / 駐車枠なし：車・人・自転車のYOLO検知だけ確認
param(
  [string]$Video = "",
  [string]$VideoDirectory = "G:\parking-movie",
  [string]$Model = "",
  [switch]$SaveVideo,
  [switch]$Loop,
  [switch]$AllFrames
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$pythonCandidates = @(
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\.venv\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  & $candidate -c "import cv2, ultralytics" 2>$null
  if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (-not $python) {
  throw "YOLOとOpenCVを使える研究用Pythonが見つかりません。研究環境を確認してください。"
}
Write-Host ""
Write-Host "========== 道の駅日光：駐車枠なしYOLO確認 =========="
Write-Host "【表示】車・トラック・バス・自転車・人・認識可能な障害物"
Write-Host "【実行】登録済みの駐車枠・駐車状況は一切使いません。"
Write-Host "【非公開】Supabase・管理者・利用者アプリへ送信しません。"
Write-Host "【原本】元動画も管理マップ59区画も変更しません。"
Write-Host "【Python】$python"
if ([string]::IsNullOrWhiteSpace($Video)) {
  if (Test-Path -LiteralPath $VideoDirectory -PathType Container) {
    $preferred = Join-Path $VideoDirectory "道の駅日光駐車場ライブカメラ_ニコニコ本陣_0533.mp4"
    if (Test-Path -LiteralPath $preferred -PathType Leaf) {
      $Video = $preferred
    } else {
      $candidates = @(Get-ChildItem -LiteralPath $VideoDirectory -File |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".mp4",".mov",".avi",".mkv",".webm")
          -and $_.Name -notmatch '^(YOLO判定_|yolo_annotated)'
          -and $_.Name -notmatch '_YOLO検知のみ_' } |
        Sort-Object Name)
      if ($candidates.Count -eq 1) {
        $Video = $candidates[0].FullName
      } elseif ($candidates.Count -gt 1) {
        Write-Host "【動画の選択】"
        for ($i=0; $i -lt $candidates.Count; $i++) {
          Write-Host ("{0}. {1}" -f ($i+1), $candidates[$i].Name)
        }
        $choiceText=(Read-Host "動画番号を入力（0でフルパスを入力）").Trim()
        $choice=0
        if ([int]::TryParse($choiceText,[ref]$choice) -and
            $choice -ge 1 -and $choice -le $candidates.Count) {
          $Video=$candidates[$choice-1].FullName
        } elseif ($choiceText -ne "0") {
          throw "動画番号が不正です。"
        }
      }
    }
  }
  if ([string]::IsNullOrWhiteSpace($Video)) {
    $Video=Read-Host "元動画のフルパス（例 G:\parking-movie\日光.mp4）"
  }
}
$Video=([string]$Video).Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Video -PathType Leaf)) { throw "元動画がありません: $Video" }
$Video=(Resolve-Path -LiteralPath $Video).Path
Write-Host "【動画】$Video"
$config=Join-Path $PSScriptRoot "config.json"
if ([string]::IsNullOrWhiteSpace($Model)) {
  $requiresModel = -not (Test-Path -LiteralPath $config -PathType Leaf)
  if (-not $requiresModel) {
    try {
      $settings = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
      $modelInConfig = ([string]$settings.vehicle_model).Trim()
      if ([string]::IsNullOrWhiteSpace($modelInConfig)) {
        $requiresModel = $true
      } else {
        $modelRelative = Join-Path $PSScriptRoot $modelInConfig
        if (-not (Test-Path -LiteralPath $modelInConfig -PathType Leaf) -and
            -not (Test-Path -LiteralPath $modelRelative -PathType Leaf)) {
          $requiresModel = $true
          Write-Host "【モデル未発見】config.jsonの重みファイル: $modelInConfig"
        }
      }
    } catch {
      $requiresModel = $true
      Write-Host "【確認】config.jsonを読み込めないため、YOLOモデルのパスを指定してください。"
    }
  }
  if ($requiresModel) {
    $Model=Read-Host "学習済みYOLOの .pt ファイルのパス（ドラッグも可）"
  }
}
if (-not [string]::IsNullOrWhiteSpace($Model)) {
  $Model=([string]$Model).Trim().Trim('"')
  if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) {
    throw "学習済みモデルがありません: $Model"
  }
  $Model=(Resolve-Path -LiteralPath $Model).Path
}
$flags=@(
  (Join-Path $PSScriptRoot "preview_nikko_no_zones.py"),
  "--video", $Video,
  "--config", $config
)
if ($Model) { $flags+=@("--model",$Model) }
if ($SaveVideo) { $flags+="--save-video" }
if ($Loop) { $flags+="--loop" }
if ($AllFrames) { $flags+="--all-frames" }
Write-Host "【操作】Q：終了／Space：一時停止／S：画像保存／R：最初から再生"
if ($Loop) { Write-Host "【再生】動画を繰り返します。終了時はQを押してください。" }
if ($SaveVideo) {
  Write-Host "【記録】検出枠を重ねたMP4を、reports_nikko_detection_onlyに保存します。"
}
& $python @flags
if ($LASTEXITCODE -ne 0) { throw "駐車枠なしのYOLO検知プレビューに失敗しました。" }
Write-Host "【終了】検知確認を終了しました。"
