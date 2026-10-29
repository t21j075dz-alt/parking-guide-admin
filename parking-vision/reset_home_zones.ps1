# 自宅駐車場のYOLO区画を、管理アプリの登録データに合わせて再登録する。
# Supabase側のデータ・録画・学習済み重みは削除しない。
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$configFile = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
  throw "【中止】config.json がありません。まずホーム駐車場_かんたん準備.cmdを実行してください。"
}
$settings = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($settings.facility_id -ne "home-test-001") {
  throw "【中止】自宅駐車場以外の設定です。既存設定を変更していません。"
}
if ([string]$settings.supabase_url -notmatch '^https://[a-z0-9-]+\.supabase\.co$' -or
    [string]::IsNullOrWhiteSpace([string]$settings.publishable_key)) {
  throw "【中止】SupabaseのURLまたは公開用キーが未設定です。"
}

Write-Host ""
Write-Host "========== 自宅駐車場 / 駐車枠リセット =========="
Write-Host "【取得】管理アプリに登録された区画をSupabaseから読み込んでいます..."
$endpoint = "$($settings.supabase_url)/rest/v1/parking_layouts?facility_id=eq.home-test-001&select=layout_data&limit=1"
try {
  $layouts = @(Invoke-RestMethod -Uri $endpoint -Headers @{ apikey = [string]$settings.publishable_key } -Method Get -TimeoutSec 15)
} catch {
  throw "【中止】登録データの取得に失敗しました。通信と閲覧権限を確認してください。config.jsonは変更していません。詳細: $($_.Exception.Message)"
}
if ($layouts.Count -ne 1 -or $null -eq $layouts[0].layout_data) {
  throw "【中止】自宅駐車場の登録データが見つかりません。config.jsonは変更していません。"
}
$spaces = @($layouts[0].layout_data.objects | Where-Object {
  $_.objectType -eq "parkingSpace"
} | Sort-Object { [string]$_.uid })
if ($spaces.Count -eq 0) {
  throw "【中止】管理アプリに駐車枠がありません。config.jsonは変更していません。"
}
$uids = @()
$labels = [ordered]@{}
foreach ($space in $spaces) {
  $uid = [string]$space.uid
  if ($uid -notmatch '^space_[A-Za-z0-9_-]+$' -or $labels.Contains($uid)) {
    throw "【中止】登録区画のUIDが不正、または重複しています。config.jsonは変更していません。"
  }
  $name = [string]$space.name
  if ([string]::IsNullOrWhiteSpace($name)) { $name = $uid }
  $uids += $uid
  $labels[$uid] = $name
}
Write-Host ""
Write-Host "【施設】自宅駐車場（home-test-001）"
Write-Host "【登録区画数】$($uids.Count) 件"
foreach ($uid in $uids) {
  Write-Host "  $uid ＝ $($labels[$uid])"
}
Write-Host ""
Write-Host "【リセット対象】PC内の駐車枠座標、入口/出口エリア、初期空車確認、区画登録時の画角記録"
Write-Host "【維持】カメラ番号 $($settings.source) / 取得方式 $($settings.camera_backend) / 学習モデル"
Write-Host "【維持】Supabaseの登録データ、過去の録画ファイル、車両の研究データ"
Write-Host "【注意】リセット後は画面の四隅をクリックして再登録するまでライブ公開できません。"
$confirmation = Read-Host "設定をバックアップしてリセットする場合のみ「リセット」と入力"
if ($confirmation -ne "リセット") {
  Write-Host "【中止】変更していません。"
  exit 0
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $PSScriptRoot "config_backup_before_zone_reset_$stamp.json"
Copy-Item -LiteralPath $configFile -Destination $backup -ErrorAction Stop
$settings | Add-Member -NotePropertyName "space_uids" -NotePropertyValue ([string[]]$uids) -Force
$settings | Add-Member -NotePropertyName "space_labels" -NotePropertyValue $labels -Force
$settings | Add-Member -NotePropertyName "space_zones" -NotePropertyValue ([pscustomobject]@{}) -Force
$settings | Add-Member -NotePropertyName "entry_zone" -NotePropertyValue @() -Force
$settings | Add-Member -NotePropertyName "exit_zone" -NotePropertyValue @() -Force
$settings | Add-Member -NotePropertyName "initially_confirmed_empty_uids" -NotePropertyValue @() -Force
$settings | Add-Member -NotePropertyName "allow_unverified_initial_empty" -NotePropertyValue $false -Force
$settings.PSObject.Properties.Remove("calibration_capture")
$json = $settings | ConvertTo-Json -Depth 40
[System.IO.File]::WriteAllText(
  $configFile, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)
)
Write-Host ""
Write-Host "【完了】YOLOの登録対象を $($uids.Count) 区画にそろえ、古い枠座標をリセットしました。"
Write-Host "【バックアップ】$backup"
Write-Host "【確認】カメラ番号 $($settings.source) / 取得方式 $($settings.camera_backend) は変更していません。"
Write-Host ""
Write-Host "【次の操作】画面の Zone: space_001 から順に四隅をクリックしてください。"
Write-Host "【画角】現在のカメラに映る駐車枠だけを登録します。映らない枠はSで飛ばし、空きとして扱いません。"
Write-Host "【操作】左クリック4回で登録 / Spaceで映像停止・再開 / qで保存 / Escでキャンセル"
$go = Read-Host "今すぐカメラ映像で駐車枠を登録しますか？ [Y/n]"
if ($go -ne "" -and $go -notmatch '^[yY]$') {
  Write-Host "【次回】既存のPython環境で calibrate.py --config config.json を実行してください。"
  exit 0
}

$pythonCandidates = @(
  (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Desktop\parking-yolo-starter\.venv\Scripts\python.exe"),
  (Join-Path $env:USERPROFILE "Downloads\parking-yolo-starter\.venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) {
  Write-Host "【注意】YOLO用のPythonが見つかりません。枠数のリセットは保存されています。"
  Write-Host "YOLO環境を確認してからかんたん準備を起動してください。"
  exit 0
}
& $python (Join-Path $PSScriptRoot "calibrate.py") --config $configFile
if ($LASTEXITCODE -ne 0) {
  throw "【注意】画面での区画登録が正常終了しませんでした。リセット済み設定とバックアップは残っています。"
}
$after = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
$done = @($after.space_zones.PSObject.Properties).Count
Write-Host "【登録結果】$done / $($uids.Count) 区画の映像座標が登録されています。"
if ($done -lt $uids.Count) {
  Write-Host "【注意】映らなかった区画は未登録のままで、安全のため空き扱いにしません。"
}
