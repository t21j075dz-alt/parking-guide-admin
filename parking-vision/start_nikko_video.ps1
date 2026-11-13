# Windows PowerShell 5.1 / 道の駅日光 録画→YOLO
# 画角に映る全区画が対象。実際の現在の空きではありません。
param(
  [string]$Video = "",
  [string]$VideoDirectory = "G:\parking-movie",
  [string]$Alignment = "",
  [int]$SpaceCount = 0,
  [string]$SpaceUids = "",
  [string]$VerifiedEmpty = "",
  [switch]$Share,
  [switch]$AllFrames,
  [switch]$Once
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
  if (Test-Path -LiteralPath $candidate -PathType Leaf) {
    & $candidate -c "import cv2, ultralytics" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
  }
}
if (-not $python) { throw "研究用Pythonが見つかりません。YOLOの環境を確認してください。" }
Write-Host "============= 道の駅日光・録画のYOLO逐次判定 ============="
Write-Host "【対象】録画内に映る全区画。画角外の区画は判定対象外です。"
Write-Host "【注意】実際の道の駅日光の現在の空き情報ではありません。"
Write-Host "【安全】自宅のconfig.jsonや実カメラは変更しません。"
Write-Host "【Python】$python"
if ([string]::IsNullOrWhiteSpace($Video)) {
  # 日光の動画はユーザー指定のGドライブを優先。原本を変更しない。
  if (Test-Path -LiteralPath $VideoDirectory -PathType Container) {
    $preferred = Join-Path $VideoDirectory "道の駅日光駐車場ライブカメラ_ニコニコ本陣_0533.mp4"
    if (Test-Path -LiteralPath $preferred -PathType Leaf) {
      $Video = $preferred
    } else {
      $videos = @(Get-ChildItem -LiteralPath $VideoDirectory -File |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".mp4", ".mov", ".avi", ".mkv", ".webm") -and
          $_.Name -notmatch '^(YOLO判定_|yolo_annotated)' } |
        Sort-Object Name)
      if ($videos.Count -eq 1) {
        $Video = $videos[0].FullName
      } elseif ($videos.Count -gt 1) {
        Write-Host "【動画の選択】$VideoDirectory"
        for ($i = 0; $i -lt $videos.Count; $i++) {
          Write-Host ("{0}. {1}" -f ($i+1), $videos[$i].Name)
        }
        $choiceText = (Read-Host "使用する動画の番号（Enterで手動入力）").Trim()
        $choice = 0
        if ([int]::TryParse($choiceText, [ref]$choice) -and $choice -ge 1 -and $choice -le $videos.Count) {
          $Video = $videos[$choice-1].FullName
        }
      }
    }
  }
  if ([string]::IsNullOrWhiteSpace($Video)) {
    $Video = Read-Host "元動画のファイル名（例：G:\parking-movie\動画.mp4）を入力"
  }
}
Write-Host "【元動画】$Video"
$Video = $Video.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Video -PathType Leaf)) { throw "元動画が見つかりません: $Video" }
$Video = (Resolve-Path -LiteralPath $Video).Path
if (-not (Test-Path -LiteralPath ".\config.json" -PathType Leaf)) {
  throw "YOLO用config.jsonがありません。先に研究用PCの環境を構築してください。"
}
$config = Join-Path $PSScriptRoot "config_nikko_video_demo.json"
$setup = Join-Path $PSScriptRoot "nikko_video_config.py"
$checkArgs = @($setup, "--config", $config, "--video", $Video, "--check")
function Test-Ready {
  & $python @checkArgs 2>$null | Out-Null
  return $LASTEXITCODE -eq 0
}
if (-not (Test-Ready)) {
  Write-Host "【準備】この録画に合う区画座標がまだ校正されていません。"
  if ([string]::IsNullOrWhiteSpace($Alignment) -and $SpaceCount -eq 0 -and [string]::IsNullOrWhiteSpace($SpaceUids)) {
    Write-Host "1. 管理マップから画角内の区画を一括投影（おすすめ）"
    Write-Host "2. 動画上ですべての区画の四隅を選んで登録"
    Write-Host "3. キャンセル"
    $selected = (Read-Host "登録方法（1/2/3）").Trim()
    if ($selected -eq "1") { $Alignment = Read-Host "管理者アプリで保存した日光の位置合わせJSONのパス" }
    elseif ($selected -eq "2") {
      $countText = (Read-Host "動画に映る駐車区画はいくつありますか（1～999）").Trim()
      $parsed = 0
      if (-not [int]::TryParse($countText, [ref]$parsed)) { throw "区画数は整数で指定してください。" }
      $SpaceCount = $parsed
    } else { Write-Host "【中止】設定は変更しません。"; return }
  }
  if (-not [string]::IsNullOrWhiteSpace($Alignment)) {
    $Alignment = $Alignment.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath $Alignment -PathType Leaf)) { throw "位置合わせJSONが見つかりません: $Alignment" }
    $arguments = @((Join-Path $PSScriptRoot "import_nikko_map_alignment.py"), "--base", "config.json", "--config", $config, "--alignment", $Alignment, "--video", $Video, "--apply")
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw "日光の区画設定を保存できませんでした。" }
  } else {
    if (-not [string]::IsNullOrWhiteSpace($SpaceUids)) {
      $idsArgs = @("--space-uids", $SpaceUids)
    } else {
      if ($SpaceCount -lt 1 -or $SpaceCount -gt 999) { throw "撮影範囲内の区画数を1～999で指定してください。" }
      $idsArgs = @("--space-count", [string]$SpaceCount)
    }
    $existing = Test-Path -LiteralPath $config -PathType Leaf
    if ($existing) {
      Write-Host "【再登録】録画設定をバックアップし、動画に合わせて校正し直します。"
      $approve = (Read-Host "既存校正をやり直す場合のみ「再登録」と入力").Trim()
      if ($approve -ne "再登録") { Write-Host "【中止】既存設定は変更しません。"; return }
    }
    $prepare = @($setup, "--base", "config.json", "--config", $config) + $idsArgs
    if ($existing) { $prepare += "--reset-zones" }
    & $python @prepare
    if ($LASTEXITCODE -ne 0) { throw "日光の録画設定が作成できませんでした。" }
    Write-Host "【四隅の登録】動画内に映る全区画を左クリック4回ずつ登録します。"
    Write-Host "【保存】Qで保存。Escでキャンセル。未登録の区画があると判定を開始できません。"
    & $python (Join-Path $PSScriptRoot "calibrate.py") --config $config --source $Video
    if ($LASTEXITCODE -ne 0) { throw "動画の区画校正に失敗しました。" }
  }
}
& $python @checkArgs
if ($LASTEXITCODE -ne 0) { throw "未登録の区画、動画の変更、または誤った校正が見つかりました。" }
$settings = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Test-Path -LiteralPath ([string]$settings.vehicle_model) -PathType Leaf)) {
  if (-not ([string]$settings.vehicle_model -match '^[A-Za-z0-9_-]+\.pt$')) {
    throw "YOLOモデルが見つかりません: $($settings.vehicle_model)"
  }
}
Write-Host "【判定対象】$(@($settings.space_uids).Count)区画"
Write-Host "【画角外】YOLOの判定や現在の空き案内には使いません。"
Write-Host "【出力】YOLO判定付き動画・区画状態CSV・追跡診断ファイル"
$flags = @("--config", $config, "--video", $Video, "--preview")
if (-not $Once) { $flags += "--loop-video" }
if ($AllFrames) {
  Write-Host "【全フレーム】精度優先。PCが遅い場合は動画より再生が遅くなります。"
  $flags += "--video-process-all-frames"
} else { Write-Host "【実時間ペース】YOLOが遅い場合は一部のフレームを飛ばします。" }
if (-not [string]::IsNullOrWhiteSpace($VerifiedEmpty)) {
  $flags += @("--verified-empty", $VerifiedEmpty)
}
if ($Share) {
  Write-Host "【録画共有】日光の録画実演専用データを利用者アプリに送ります。"
  $approve = (Read-Host "共有する場合だけ「録画共有」と入力").Trim()
  if ($approve -ne "録画共有") { Write-Host "【中止】共有しません。"; return }
  $flags += "--demo-publish"
  Write-Host "【画像共有】過去の録画の縮小静止画を約5秒ごとに全アプリへ反映できます。"
  Write-Host "【注意】画像には常に「録画・現地ライブではない」と表示します。"
  $photoApproval = (Read-Host "静止画も公開する場合だけ「写真も共有」と入力").Trim()
  if ($photoApproval -eq "写真も共有") {
    $flags += "--share-recorded-stills"
  } else {
    Write-Host "【画像共有OFF】区画の状態だけを管理者・利用者アプリへ反映します。"
  }
} else {
  Write-Host "【PC内だけ】クラウドへ送信しません。"
  $flags += "--dry-run"
}
& $python (Join-Path $PSScriptRoot "monitor.py") @flags
if ($LASTEXITCODE -ne 0) { throw "日光の録画YOLOが異常終了しました。" }
Write-Host "【終了】日光の録画判定を停止しました。"
