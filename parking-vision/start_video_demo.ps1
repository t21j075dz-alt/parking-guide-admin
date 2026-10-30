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

# 録画用の6区画が未登録なら、リアルタイムカメラの座標を目視確認して再利用。
# 動画の画角が異なる場合は、この動画専用に再登録。実カメラの設定は上書きしない。
$videoSettings = Get-Content -LiteralPath $demoConfig -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedZoneIds = @("space_001", "space_002", "space_003", "space_004", "space_005", "space_006")
function Test-VideoZones($settings) {
  if ([string]$settings.facility_id -ne "home-video-demo-001") {
    throw "録画専用設定の施設IDが異なります。実ライブの施設へ録画を送信しません。"
  }
  $areas = $settings.space_zones
  if ($null -eq $areas) { return $false }
  $zoneKeys = @($areas.PSObject.Properties | ForEach-Object { $_.Name })
  if ($zoneKeys.Count -ne 6) { return $false }
  foreach ($uid in $expectedZoneIds) {
    if ($uid -notin $zoneKeys) { return $false }
    $polygon = @($areas.$uid)
    if ($polygon.Count -ne 4) { return $false }
  }
  return $true
}

if (-not (Test-VideoZones $videoSettings)) {
  Write-Host ""
  Write-Host "【駐車区画の確認】録画実演用の6区画が未登録です。"
  Write-Host "1. リアルタイムカメラで登録済みの6区画を動画に重ねて流用"
  Write-Host "2. この動画の画角に合わせて6区画を新しく登録"
  Write-Host "3. 取り消す（クラウド送信しない）"
  $zoneChoice = (Read-Host "区画の設定方法（1/2/3）").Trim()
  if ($zoneChoice -eq "1") {
    $sourceCandidates = @(
      (Join-Path $PSScriptRoot "config_usb_original.json"),
      (Join-Path $PSScriptRoot "config_laptop_original.json"),
      (Join-Path $PSScriptRoot "config_from_laptop.json"),
      (Join-Path $PSScriptRoot "config_from_laptop_fixed.json"),
      "D:\config.json"
    )
    $sourceConfig = $null
    foreach ($candidate in $sourceCandidates) {
      if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
      try {
        $previous = Get-Content -LiteralPath $candidate -Raw -Encoding UTF8 | ConvertFrom-Json
        $previousKeys = @($previous.space_zones.PSObject.Properties | ForEach-Object { $_.Name })
        if ($previous.facility_id -eq "home-test-001" -and
            $previousKeys.Count -eq 6 -and
            @($expectedZoneIds | Where-Object { $_ -notin $previousKeys }).Count -eq 0) {
          $sourceConfig = $candidate
          break
        }
      } catch {
        Write-Host "【参考】読み取れない旧設定をスキップ: $candidate"
      }
    }
    if (-not $sourceConfig) {
      $manualPath = (Read-Host "6区画が登録済みのJSONをフルパスで入力（Enterで中止）").Trim().Trim('"')
      if (-not $manualPath -or -not (Test-Path -LiteralPath $manualPath -PathType Leaf)) {
        throw "移行元の6区画設定が見つかりません。区画登録をせずに終了します。"
      }
      $sourceConfig = $manualPath
    }
    Write-Host "【移行元】$sourceConfig"
    Write-Host "【重要】動画と実カメラの位置・向き・レンズ・ズームが違えばQで中止してください。"
    $importArgs = @((Join-Path $PSScriptRoot "reuse_live_zones_for_video.py"),
      "--source-config", $sourceConfig, "--demo-config", $demoConfig, "--video", $Video)
    & $python @importArgs
    if ($LASTEXITCODE -ne 0) {
      throw "既存区画の取り込みに失敗しました。上の説明をご確認ください。"
    }
  } elseif ($zoneChoice -eq "2") {
    Write-Host "【動画専用の区画登録】映像内で四隅を4点ずつ指定します。Q=保存 / Esc=中止。"
    & $python (Join-Path $PSScriptRoot "calibrate.py") --config $demoConfig --source $Video
    if ($LASTEXITCODE -ne 0) {
      throw "動画での区画登録に失敗しました。上の説明をご確認ください。"
    }
  } else {
    Write-Host "【中止】区画が未登録のため、判定も共有も開始していません。"
    return
  }

  $videoSettings = Get-Content -LiteralPath $demoConfig -Raw -Encoding UTF8 | ConvertFrom-Json
  if (-not (Test-VideoZones $videoSettings)) {
    Write-Host "【中止】録画用の6区画を確認できませんでした。全区画が動画に一致することを確認して設定してください。"
    return
  }
}
if (-not (Test-Path -LiteralPath ([string]$videoSettings.vehicle_model) -PathType Leaf)) {
  throw "学習モデルが見つかりません。config_video_demo.json のvehicle_modelを確認してください。"
}
Write-Host "【映像】$Video"
Write-Host "【AIモデル】$($videoSettings.vehicle_model)"
# 研究発表用の録画実演では、QまたはCtrl+Cで止めるまで同じ動画を繰り返す。
$flags = @("--config", $demoConfig, "--video", $Video, "--loop-video", "--preview")
Write-Host "【ループ】動画が終わると自動で先頭に戻ります。QキーまたはCtrl+Cで停止します。"
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
