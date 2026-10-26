# 駐車場AI 卒業研究・かんたん実行ツール
# 使い方：PowerShellで .\start.ps1（動画テスト）
# 動画・写真・録画は研究PCにだけ保存し、勝手に公開しない。
param(
  [ValidateSet("video", "calibrate", "camera", "cloud", "label", "train")]
  [string]$Mode = "video",
  [string]$Video = "",
  [string]$Images = "",
  [string]$ValidationImages = "",
  [string]$Python = "",
  [switch]$Preview,
  [switch]$SaveVideo
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "=============================================="
Write-Host "   駐車場AI / かんたん実行ツール"
Write-Host "=============================================="
Write-Host "動画や写真をクラウドへ勝手に送信しません。"
Write-Host ""

# 以前使っていたYOLOのPythonを指定すれば環境を作り直さずに済む。
$pythonCommand = if ($Python) {
  if (-not (Test-Path -LiteralPath $Python)) { throw "指定されたPythonが見つかりません: $Python" }
  (Resolve-Path -LiteralPath $Python).Path
} elseif (Test-Path ".\.venv\Scripts\python.exe") {
  (Resolve-Path ".\.venv\Scripts\python.exe").Path
} else {
  "python"
}

& $pythonCommand -c "import sys; print('使用するPython:', sys.executable)"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Pythonを起動できません。WindowsでPythonをインストールするか -Python オプションで指定してください。"
  exit 1
}

$config = Join-Path $PSScriptRoot "config.json"
if ($Mode -in @("video", "calibrate", "camera", "cloud")) {
  if (-not (Test-Path -LiteralPath $config)) {
    Copy-Item (Join-Path $PSScriptRoot "config.example.json") $config
    Write-Host "初回設定のため config.json を作成しました。"
    Write-Host "管理アプリの施設ID、クラウドの公開用キーと区画IDを確認して保存してください。"
    Write-Host "保存後にこのコマンドをもう一度実行してください。"
    Start-Process notepad.exe -ArgumentList ('"' + $config + '"')
    exit 0
  }
}

if ($Mode -in @("video", "calibrate") -and -not $Video) {
  $Video = Read-Host "撮影した動画のフルパスを入力してください（例: C:\parking\test_house1.mp4）"
}
if ($Mode -in @("video", "calibrate") -and -not (Test-Path -LiteralPath $Video -PathType Leaf)) {
  throw "動画ファイルが見つかりません。フルパスを確認してください: $Video"
}

switch ($Mode) {
  "video" {
    Write-Host "【録画動画の解析】クラウドには書き込みません。"
    # 最初の1回はカメラの写真と駐車枠の位置を結びつける。
    # 初心者でも「動画を開始」だけで登録手順に進める。
    $settings = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
    $zones = @($settings.space_zones.PSObject.Properties)
    if ($zones.Count -eq 0) {
      Write-Host "カメラに写る駐車枠がまだ登録されていません。"
      Write-Host "四隅を順番に4回クリックして登録してください。"
      & $pythonCommand "calibrate.py" "--config" $config "--source" $Video
      if ($LASTEXITCODE -ne 0) { throw "駐車枠の登録が完了しませんでした。" }
      $settings = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
      if (@($settings.space_zones.PSObject.Properties).Count -eq 0) {
        throw "登録された駐車枠がありません。映像上で1つ以上の枠を登録してください。"
      }
      Write-Host "駐車枠の登録が完了しました。続けて動画を分析します。"
    }
    $argsForPython = @("analyze_video.py", "--config", $config, "--video", $Video)
    if ($Preview) { $argsForPython += "--preview" }
    if ($SaveVideo) { $argsForPython += "--save-video" }
    & $pythonCommand @argsForPython
    break
  }
  "calibrate" {
    Write-Host "【枠の登録】動画の駐車区画を四隅で登録してください。"
    & $pythonCommand "calibrate.py" "--config" $config "--source" $Video
    break
  }
  "camera" {
    Write-Host "【カメラのテスト】判定は表示しますが、クラウドへは保存しません。"
    & $pythonCommand "monitor.py" "--config" $config "--preview" "--dry-run"
    break
  }
  "cloud" {
    Write-Host "【カメラの共有】リアルタイムデータをSupabaseへ送信します。"
    Write-Host "先にカメラと区画の判定を目視で確認してください。"
    $answer = Read-Host "送信を開始する場合のみ「共有」と入力してください"
    if ($answer -ne "共有") { Write-Host "共有しませんでした。"; exit 0 }
    & $pythonCommand "monitor.py" "--config" $config "--preview"
    break
  }
  "label" {
    if (-not $Images) { $Images = Read-Host "カラーコーンなどを撮影した写真フォルダを入力" }
    if (-not (Test-Path -LiteralPath $Images -PathType Container)) {
      throw "写真フォルダが見つかりません: $Images"
    }
    $argsForPython = @("label_obstacles.py", "--images", $Images)
    if ($ValidationImages) { $argsForPython += @("--validation-images", $ValidationImages) }
    & $pythonCommand @argsForPython
    break
  }
  "train" {
    if (-not (Test-Path -LiteralPath ".\dataset\data.yaml")) {
      Write-Host "正解ラベルがありません。まず -Mode label で写真に四角をつけてください。"
      exit 1
    }
    $device = Read-Host "学習する環境（CPUならcpu／CUDA対応GPUなら0）[cpu]"
    if (-not $device) { $device = "cpu" }
    & $pythonCommand "train_obstacles.py" "--data" ".\dataset\data.yaml" "--device" $device
    break
  }
}
if ($LASTEXITCODE -ne 0) {
  Write-Host "処理が完了しませんでした。上に表示された説明を確認してください。"
  exit $LASTEXITCODE
}
Write-Host "完了しました。解析結果は reports フォルダ、学習用データは dataset フォルダに保存されます（モードによります）。"
