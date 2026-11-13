# Windows PowerShell 5.1 / 日光・位置合わせJSON -> ループYOLO -> 管理・利用者アプリ
# 管理者アプリから「確認済み設定JSON」を保存してから使用すること。
# 自宅・他施設の設定や元動画は変更しない。実行と写真共有には明示承認が必要。
param(
  [string]$Alignment = "",
  [string]$Video = "",
  [string]$VideoDirectory = "G:\parking-movie"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-NikkoExport($path) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
  try {
    $data = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($data.schema_version -ne 1 -or
        $data.facility_id -ne "nikko-test-001" -or
        $data.camera_id -ne "nikko-recording-01") { return $false }
    if ($null -eq $data.space_zones -or @($data.space_uids).Count -lt 1) { return $false }
    return $true
  } catch {
    return $false
  }
}

function Find-NikkoExports {
  # Chrome/Edgeの一般的な保存先と録画フォルダ内だけを検索。
  # 最新ファイルを黙って選ばず、必ず本人に選んでもらう。
  $folders = @(
    (Join-Path $env:USERPROFILE "Downloads"),
    (Join-Path $env:USERPROFILE "Desktop"),
    $VideoDirectory,
    $PSScriptRoot
  ) | Select-Object -Unique
  $found = @()
  foreach ($folder in $folders) {
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
    foreach ($entry in @(Get-ChildItem -LiteralPath $folder -File -Filter "camera-map-alignment-*.json" -ErrorAction SilentlyContinue)) {
      if (Test-NikkoExport $entry.FullName) { $found += $entry }
    }
  }
  return @($found | Sort-Object LastWriteTime -Descending | Select-Object -Unique)
}

Write-Host ""
Write-Host "======================================================"
Write-Host " 道の駅日光: 録画ループYOLO -> 全アプリに反映"
Write-Host "======================================================"
Write-Host "【施設】道の駅日光（録画実験）"
Write-Host "【動画フォルダ】$VideoDirectory"
Write-Host "【重要】過去録画の実演です。現地のライブ映像・現在の空き情報ではありません。"
Write-Host "【対象外】画角外または写真で未登録の区画は空き案内しません。"
Write-Host ""

if ([string]::IsNullOrWhiteSpace($Alignment)) {
  $candidates = @(Find-NikkoExports)
  if ($candidates.Count -gt 0) {
    Write-Host "【発見】日光専用の位置合わせJSON $($candidates.Count)件"
    for ($i = 0; $i -lt $candidates.Count; $i++) {
      Write-Host ("{0}. {1}  [更新 {2}]" -f ($i + 1),
        $candidates[$i].FullName, $candidates[$i].LastWriteTime.ToString("yyyy/MM/dd HH:mm"))
    }
    Write-Host "0. 手動でJSONのパスを入力する"
    $choice = (Read-Host "反映するJSON番号（Enterで中止）").Trim()
    if (-not $choice) { Write-Host "【中止】未選択です。"; return }
    $number = 0
    if (-not [int]::TryParse($choice, [ref]$number)) { throw "番号を指定してください。" }
    if ($number -gt 0 -and $number -le $candidates.Count) {
      $Alignment = $candidates[$number - 1].FullName
    } elseif ($number -ne 0) {
      throw "指定された番号のファイルはありません。"
    }
  }
  if ([string]::IsNullOrWhiteSpace($Alignment)) {
    Write-Host "【案内】管理者アプリの「確認済み設定JSONを保存」で出力してください。"
    $Alignment = Read-Host "位置合わせJSONのフルパス（Enterで中止）"
  }
}
$Alignment = ([string]$Alignment).Trim().Trim('"')
if (-not $Alignment) { Write-Host "【中止】クラウドへの公開を開始しません。"; return }
if (-not (Test-NikkoExport $Alignment)) {
  throw "道の駅日光の位置合わせJSONとして確認できません: $Alignment"
}
$Alignment = (Resolve-Path -LiteralPath $Alignment).Path
Write-Host "【取込み元】$Alignment"
Write-Host "【安全】JSONを検証し、元動画の先頭・中間・末尾に枠を重ねて確認します。"
Write-Host "【公開】追加の「録画共有」と「写真も共有」の承認がない限り勝手に公開しません。"

$starter = Join-Path $PSScriptRoot "start_nikko_video.ps1"
if (-not (Test-Path -LiteralPath $starter -PathType Leaf)) {
  throw "録画YOLO起動スクリプトがありません: $starter"
}
if ([string]::IsNullOrWhiteSpace($Video)) {
  & $starter -Alignment $Alignment -VideoDirectory $VideoDirectory -Share
} else {
  & $starter -Alignment $Alignment -Video $Video -VideoDirectory $VideoDirectory -Share
}
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
  throw "日光録画のYOLO・アプリ連携が異常終了しました。"
}
