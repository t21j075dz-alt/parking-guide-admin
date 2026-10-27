# 自宅駐車場を、管理アプリの区画IDと固定カメラに安全に結び付ける。
# 既存config.jsonは上書きしない。映像もSupabaseへ送信しない。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$home = $env:USERPROFILE
$configFile = Join-Path $PSScriptRoot "config.json"
$example = Join-Path $PSScriptRoot "config.example.json"
$syncFile = Join-Path (Split-Path $PSScriptRoot -Parent) "sync-config.js"

Write-Host ""
Write-Host "========== 自宅駐車場：かんたん準備 =========="
Write-Host "【安全】今回はカメラの判定テストだけ。Supabaseへ送信・一般公開しません。"

$pythonCandidates = @(
  (Join-Path $home "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $home "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) { throw "【エラー】研究用Pythonが見つかりません。デスクトップまたはノートPCのYOLO環境を確認してください。" }
& $python -c "import cv2, ultralytics; print('【確認】YOLOと動画処理を利用できます')"
if ($LASTEXITCODE -ne 0) { throw "【エラー】YOLOを実行できません。Python環境を確認してください。" }

if (-not (Test-Path -LiteralPath $configFile)) {
  if (-not (Test-Path -LiteralPath $example)) { throw "初期設定ファイルが見つかりません" }
  if (-not (Test-Path -LiteralPath $syncFile)) { throw "管理アプリの接続設定が見つかりません" }
  $syncText = Get-Content -LiteralPath $syncFile -Raw
  if ($syncText -notmatch 'supabaseUrl:\s*"([^"]+)"') { throw "Supabaseの接続先が見つかりません" }
  $url = $Matches[1]
  if ($syncText -notmatch 'publishableKey:\s*"([^"]+)"') { throw "Supabaseの公開用キーが見つかりません" }
  $publishable = $Matches[1]
  if ($url -notmatch '^https://[a-z0-9-]+\.supabase\.co$' -or $publishable -notmatch '^sb_publishable_') {
    throw "SupabaseのURLまたは公開用キーが不正です"
  }

  # 管理アプリで既に登録されている枠だけを選ばせる（映像上のP001とUIDは別物）。
  $endpoint = "$url/rest/v1/parking_layouts?facility_id=eq.home-test-001&select=layout_data&limit=1"
  try {
    $layouts = @(Invoke-RestMethod -Uri $endpoint -Headers @{ apikey = $publishable } -Method Get -TimeoutSec 10)
  } catch {
    throw "Supabaseの既存区画を取得できません。インターネット接続を確認してください。"
  }
  if ($layouts.Count -ne 1 -or -not $layouts[0].layout_data) {
    throw "home-test-001 の駐車場レイアウトが見つかりません。Supabaseを確認してください。"
  }
  $spaces = @($layouts[0].layout_data.objects | Where-Object {
    $_.objectType -eq "parkingSpace" -and $_.uid -match '^space_[A-Za-z0-9_-]+$'
  })
  if ($spaces.Count -eq 0) { throw "管理アプリで登録した駐車枠がありません" }

  Write-Host ""
  Write-Host "【1】映像の実際の駐車枠に対応する、管理アプリの区画を選んでください。"
  Write-Host "　P001は映像で付けた仮名です。space_001と同じとは限りません。"
  for ($i = 0; $i -lt $spaces.Count; $i++) {
    Write-Host (" {0}: {1} （{2}）" -f ($i+1), $spaces[$i].name, $spaces[$i].uid)
  }
  $choice = Read-Host "番号を入力"
  $number = 0
  if (-not [int]::TryParse($choice, [ref]$number) -or $number -lt 1 -or $number -gt $spaces.Count) {
    throw "【中止】駐車枠の番号が正しくありません。"
  }
  $selectedSpace = $spaces[$number - 1]
  Write-Host "【選択】$($selectedSpace.name) / $($selectedSpace.uid)"

  Write-Host ""
  Write-Host "【2】実際に映っているカメラを指定してください。"
  Write-Host "USBカメラが1台なら通常は 0 です。IPカメラならRTSPのURLです。"
  $sourceText = Read-Host "カメラ番号またはRTSP URL [0]"
  if ([string]::IsNullOrWhiteSpace($sourceText)) { $sourceText = "0" }
  if ($sourceText -notmatch '^\d+$' -and $sourceText -notmatch '^rtsps?://') {
    throw "【中止】録画ファイルや不明なカメラ入力はライブ共有用に登録できません。"
  }
  $source = if ($sourceText -match '^\d+$') { [int]$sourceText } else { $sourceText }

  $models = @(
    (Join-Path $home "parking-yolo-home\runs\parking_objects\visdrone_finetune_v1\weights\best.pt"),
    (Join-Path $home "parking-vision\weights\visdrone_finetune_best.pt")
  )
  $model = $models | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
  if (-not $model) { throw "【中止】研究で学習したbest.ptが見つかりません。元ファイルは変更していません。" }

  $settings = Get-Content -LiteralPath $example -Raw -Encoding UTF8 | ConvertFrom-Json
  $settings.facility_id = "home-test-001"
  $settings.camera_id = "home-camera-01"
  $settings.supabase_url = $url
  $settings.publishable_key = $publishable
  $settings.source = $source
  $settings.vehicle_model = [string]$model
  $settings.obstacle_model = "" # 追加学習モデルが完成するまで無効
  $settings.image_size = 640
  $settings.space_uids = @([string]$selectedSpace.uid)
  $settings.space_zones = [pscustomobject]@{}
  $settings.initially_confirmed_empty_uids = @()
  $settings.allow_unverified_initial_empty = $false
  $json = $settings | ConvertTo-Json -Depth 20
  # Windows PowerShellのBOMでPythonのjson.loadsがエラーにならないようUTF8-BOMなしで保存
  [System.IO.File]::WriteAllText($configFile, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
  Write-Host "【保存】PC内だけにconfig.jsonを作成しました（GitHubには送信しません）"
} else {
  $settings = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($settings.facility_id -ne "home-test-001") { throw "既存config.jsonは別施設です。上書きしません。設定を確認してください。" }
  Write-Host "【再利用】既存のconfig.jsonを変更せずに使います。"
  Write-Host "【登録区画】$(@($settings.space_uids) -join ', ')"
}

# 撮影範囲が未登録なら、実際のカメラを見ながら登録。過去の録画のP001座標は流用しない。
$zones = @($settings.space_zones.PSObject.Properties)
if ($zones.Count -eq 0) {
  Write-Host ""
  Write-Host "【3】画面上で実際の駐車枠の角を4か所クリックします。"
  Write-Host "【操作】左クリック×4 → 自動登録 → qで保存して終了"
  Write-Host "【注意】カメラを動かした場合は、もう一度登録する必要があります。"
  & $python (Join-Path $PSScriptRoot "calibrate.py") --config $configFile
  if ($LASTEXITCODE -ne 0) { throw "【エラー】枠の登録ができませんでした" }
  $settings = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
  if (@($settings.space_zones.PSObject.Properties).Count -eq 0) {
    throw "【中止】駐車枠が登録されていません。枠を4か所指定してください。"
  }
}
Write-Host ""
Write-Host "【準備完了】カメラ画面の枠設定ができています。"
Write-Host "【対応中】車両・人（障害物候補）を判定。コーン・カートの専用認識は追加学習が必要。"
Write-Host "【安全】空き未確認は unknown。今はインターネットへ判定データを送りません。"
$go = Read-Host "今すぐクラウド送信なしでカメラ判定を表示しますか？ [Y/n]"
if ($go -eq "" -or $go -match '^[yY]$') {
  Write-Host "【操作】映像画面で q を押すと終了します。"
  & $python (Join-Path $PSScriptRoot "monitor.py") --config $configFile --preview --dry-run
  if ($LASTEXITCODE -ne 0) { throw "カメラ判定でエラーが発生しました。上の表示を確認してください。" }
}
Write-Host "【次の操作】共有する際は ホーム駐車場_ライブ共有.cmd を起動してください。"
