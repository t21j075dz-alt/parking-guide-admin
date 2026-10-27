# 本物の固定カメラ映像だけをクラウドへ送る。
# 動画・写真・車両ナンバーをSupabaseへアップロードしない。
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$configFile = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
  throw "【準備不足】先に「ホーム駐車場_かんたん準備.cmd」を実行してください。"
}
$settings = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($settings.facility_id -ne "home-test-001") {
  throw "【中止】この起動ファイルは自宅テスト施設専用です。"
}
$zones = @($settings.space_zones.PSObject.Properties)
if ($zones.Count -eq 0) {
  throw "【準備不足】カメラ画面の駐車枠を登録してください。"
}
if ($settings.allow_unverified_initial_empty -eq $true) {
  throw "【中止】未確認の空きを許可する危険な設定です。falseに戻してください。"
}
if ($null -eq $settings.source -or $settings.source -eq "" -or
    $settings.camera_verified_external -ne $true -or [string]$settings.source -notmatch '^\d+$') {
  throw "【中止】外付けUSB Webカメラが確認されていません。かんたん準備から選択してください。"
}
if ($settings.source -is [string]) {
  if ($settings.source -notmatch '^rtsps?://' -and $settings.source -notmatch '^\d+$') {
    throw "【中止】録画ファイルや未対応の映像入力を現在の空き情報として共有しません。"
  }
}
if ($settings.obstacle_model -and -not (Test-Path -LiteralPath $settings.obstacle_model -PathType Leaf)) {
  throw "【中止】設定されたカラーコーン等の追加モデルが見つかりません。"
}
if (-not (Test-Path -LiteralPath $settings.vehicle_model -PathType Leaf)) {
  throw "【中止】車両判定に必要な学習済みモデルが見つかりません。"
}
$registered = @($settings.space_uids)
foreach ($property in $zones) {
  if ($property.Name -notin $registered) { throw "【中止】登録外の区画UIDがあります: $($property.Name)" }
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
if (-not $python) { throw "【中止】研究用Pythonが見つかりません" }
Write-Host ""
Write-Host "========== 駐車場ライブ判定・共有 =========="
Write-Host "施設：home-test-001"
Write-Host "映像で登録した区画：$($zones.Count)件"
Write-Host "【公開状態】公開するかは管理者アプリで別に設定します。勝手に公開ONにはしません。"
Write-Host "【注意】学習済みモデルにカラーコーン・カートのクラスがなければ、それらの認識は未対応です。"
Write-Host "【注意】誤検出、通信断、時間切れは空車を確定せず「確認できない」として扱います。"
Write-Host "【注意】実カメラの画角と枠の設定がずれていないか目視で確認してください。"
Write-Host ""
Write-Host "ログイン後に、駐車枠の状態と匿名の車両追跡データをSupabaseへ送信します。"
Write-Host "動画映像・写真・ナンバープレートは送信しません。"
Write-Host "【録画】ライブ実行中は自動でPC内に録画します（音声なし・10分ごとに分割）。"
$consent = Read-Host "実カメラで共有を開始する場合のみ「共有」と入力"
if ($consent -ne "共有") {
  Write-Host "【中止】クラウドには送信していません。"
  exit 0
}
# 昨日と同じ番号でもカメラが入れ替わる場合があるため、毎回映像を確認する。
& $python (Join-Path $PSScriptRoot "select_external_camera.py") --config $configFile --check-only
if ($LASTEXITCODE -ne 0) { throw "【中止】外付けUSB Webカメラを確認できなかったため共有しません。" }
Write-Host ""
Write-Host "Supabaseの管理者アカウントでログインしてください。"
Write-Host "パスワードは画面に表示されません。映像を終了するときは q を押します。"
& $python (Join-Path $PSScriptRoot "monitor.py") --config $configFile --preview
if ($LASTEXITCODE -ne 0) {
  throw "【エラー】ライブ判定の開始または通信に失敗しました。上の説明を確認してください。"
}
Write-Host "【終了】カメラ共有と録画を停止しました。アプリでは20秒以上経過した情報を「未確認」とします。"
Write-Host "【再生】「録画フォルダを開く.cmd」で保存済みの映像を確認できます。"
