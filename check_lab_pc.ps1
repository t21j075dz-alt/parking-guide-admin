# Laboratory PC migration check (read-only)
# Run: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\check_lab_pc.ps1
# Video: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\check_lab_pc.ps1 -VideoPath "E:\Research\original.mp4"
# This script never uploads files or changes configuration.
param(
    [string]$VideoPath = ""
)

$ErrorActionPreference = "Stop"
$homeFolder = $env:USERPROFILE
$adminFolder = Join-Path $homeFolder "parking-guide-admin"
$userFolder = Join-Path $homeFolder "parking-guide-user"
$researchFolder = Join-Path $homeFolder "parking-vision"
$cameraFolder = Join-Path $adminFolder "parking-vision"
$python = Join-Path $researchFolder ".venv-cpu\Scripts\python.exe"

function Report([string]$status, [string]$label, [string]$details) {
    Write-Host ("[{0}] {1}: {2}" -f $status, $label, $details)
}

Write-Host ""
Write-Host "===== 研究室PC 研究環境・移行状況チェック ====="
Write-Host "PCのファイルを読み取るだけです。クラウド送信や設定変更は行いません。"
Write-Host ""

Write-Host "【1】研究プログラム"
foreach ($entry in @(
    @{ Label = "管理者アプリ"; Path = (Join-Path $adminFolder "index.html") },
    @{ Label = "ユーザーアプリ"; Path = (Join-Path $userFolder "index.html") },
    @{ Label = "YOLO研究本体"; Path = (Join-Path $researchFolder "run_parking.py") },
    @{ Label = "録画・ライブ判定プログラム"; Path = (Join-Path $cameraFolder "monitor.py") }
)) {
    if (Test-Path -LiteralPath $entry.Path -PathType Leaf) {
        Report "OK" $entry.Label "あり"
    } else {
        Report "NG" $entry.Label ("見つかりません: " + $entry.Path)
    }
}

Write-Host ""
Write-Host "【2】Python・YOLO"
if (Test-Path -LiteralPath $python -PathType Leaf) {
    Report "OK" "研究用Python" $python
    & $python -c "import cv2, ultralytics, torch; print('  Python packages OK | YOLO:', ultralytics.__version__, '| OpenCV:', cv2.__version__, '| CUDA:', torch.cuda.is_available())"
    if ($LASTEXITCODE -ne 0) {
        Report "NG" "Pythonライブラリ" "importに失敗しました"
    }
} else {
    Report "NG" "研究用Python" "仮想環境が見つかりません"
}

Write-Host ""
Write-Host "【3】学習済みYOLOモデル"
$modelCandidates = @(
    (Join-Path $researchFolder "weights\visdrone_finetune_best.pt"),
    (Join-Path $homeFolder "parking-yolo-home\runs\parking_objects\visdrone_finetune_v1\weights\best.pt")
)
$modelsFound = @()
foreach ($model in $modelCandidates) {
    if (Test-Path -LiteralPath $model -PathType Leaf) {
        $modelsFound += $model
        $item = Get-Item -LiteralPath $model
        $hash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash
        Report "OK" "学習済みモデル" ("{0} | {1:N1} MB | SHA256: {2}" -f $model, ($item.Length / 1MB), $hash)
    }
}
if ($modelsFound.Count -eq 0) {
    Report "NG" "学習済みモデル" "標準の2か所に見つかりません。別の場所に置いた場合は設定内の参照先も確認してください。"
}

$baselineModel = Join-Path $researchFolder "weights\baseline_yolo11n.pt"
if (Test-Path -LiteralPath $baselineModel -PathType Leaf) {
    Report "OK" "標準YOLO11n（代替モデル）" ("{0} / 以前の独自学習済みbest.ptとは異なります" -f $baselineModel)
} else {
    Report "参考" "標準YOLO11n（代替モデル）" "未取得"
}

Write-Host ""
Write-Host "【4】カメラ・録画の設定ファイル"
$configs = @(
    @{ Name = "config_video_demo.json"; Label = "録画ループ用"; ExpectedId = "home-video-demo-001" },
    @{ Name = "config.json"; Label = "USBカメラ用"; ExpectedId = "home-test-001" },
    @{ Name = "config_camo.json"; Label = "Camo用"; ExpectedId = "home-test-001" }
)
foreach ($entry in $configs) {
    $file = Join-Path $cameraFolder $entry.Name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        Report "NG" $entry.Label ("未配置: " + $entry.Name)
        continue
    }

    Report "OK" $entry.Label ("ファイルあり: " + $entry.Name)
    try {
        $settings = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Report "NG" $entry.Label "JSONとして読み取れません"
        continue
    }
    if ([string]$settings.facility_id -eq $entry.ExpectedId) {
        Report "OK" "施設ID" ([string]$settings.facility_id)
    } else {
        Report "要確認" "施設ID" ("想定と異なります: " + [string]$settings.facility_id)
    }
    $configuredModel = [string]$settings.vehicle_model
    if ([string]::IsNullOrWhiteSpace($configuredModel)) {
        Report "NG" "モデル参照先" "vehicle_modelが空欄です"
    } else {
        if ([System.IO.Path]::IsPathRooted($configuredModel)) {
            $resolvedModel = $configuredModel
        } else {
            $resolvedModel = Join-Path $cameraFolder $configuredModel
        }
        if (Test-Path -LiteralPath $resolvedModel -PathType Leaf) {
            Report "OK" "モデル参照先" $resolvedModel
        } else {
            Report "NG" "モデル参照先" ("ファイルがありません: " + $resolvedModel)
        }
    }
    $spaceZones = $settings.space_zones
    $zoneCount = 0
    if ($null -ne $spaceZones) {
        $zoneCount = @($spaceZones.PSObject.Properties).Count
    }
    if ($zoneCount -gt 0) {
        Report "OK" "登録済みカメラ区画" ("{0}件（画角との一致は目視確認が必要）" -f $zoneCount)
    } else {
        Report "要確認" "登録済みカメラ区画" "0件。対応する映像の区画登録を確認してください"
    }
}
if (Test-Path -LiteralPath (Join-Path $cameraFolder "config_from_laptop.json") -PathType Leaf) {
    Report "OK" "旧ノートPC区画設定" "config_from_laptop.jsonあり"
} elseif (Test-Path -LiteralPath (Join-Path $cameraFolder "config_from_laptop_fixed.json") -PathType Leaf) {
    Report "OK" "旧ノートPC区画設定" "config_from_laptop_fixed.jsonあり"
} else {
    Report "参考" "旧ノートPC区画設定" "見つかりません（録画用configがあれば必須ではありません）"
}

Write-Host ""
Write-Host "【5】録画元動画"
if (-not [string]::IsNullOrWhiteSpace($VideoPath)) {
    $specifiedVideo = $VideoPath.Trim().Trim('"')
    if (Test-Path -LiteralPath $specifiedVideo -PathType Leaf) {
        $videoItem = Get-Item -LiteralPath $specifiedVideo
        if ($videoItem.Extension -in @(".mp4", ".avi", ".mov", ".mkv", ".webm")) {
            Report "OK" "指定された動画" ("{0} | {1:N1} MB" -f $videoItem.FullName, ($videoItem.Length / 1MB))
        } else {
            Report "要確認" "指定された動画" "ファイルはありますが一般的な動画拡張子ではありません"
        }
    } else {
        Report "NG" "指定された動画" ("見つかりません: " + $specifiedVideo)
    }
} else {
    $candidateFolders = @(
        (Join-Path $homeFolder "Videos"),
        (Join-Path $homeFolder "Desktop"),
        (Join-Path $homeFolder "Downloads"),
        (Join-Path $researchFolder "data"),
        (Join-Path $homeFolder "parking-yolo-home\data"),
        (Join-Path $cameraFolder "recordings")
    )
    $found = @()
    foreach ($folder in $candidateFolders) {
        if (Test-Path -LiteralPath $folder -PathType Container) {
            $found += @(Get-ChildItem -LiteralPath $folder -File -Filter "*.mp4" -ErrorAction SilentlyContinue | Select-Object -First 4)
        }
    }
    if ($found.Count -gt 0) {
        foreach ($videoItem in ($found | Select-Object -First 8)) {
            Report "候補" "MP4" $videoItem.FullName
        }
    }
    Report "未確認" "録画元動画" "元の映像_001.mp4等の正確なパスが不明です。-VideoPathで指定してください。"
}

Write-Host ""
Write-Host "【結果の読み方】"
Write-Host "OK = ファイルの存在・基本的な読み取りを確認"
Write-Host "NG = ファイル不足や参照先の不整合"
Write-Host "要確認 = カメラ画角、映像など実際の動作確認が必要"
Write-Host "注意: ファイルがあっても正しい学習済みモデル・映像であることまでは証明できません。"
Write-Host "秘密鍵、パスワード、設定JSONの中身は表示していません。"
