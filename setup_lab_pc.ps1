# 研究室PCに卒業研究の共通環境を準備する（Windows PowerShell）
# 使い方:
# powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\setup_lab_pc.ps1"
# 学習済みモデルが手元にある場合:
# powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\setup_lab_pc.ps1" -ModelPath "E:\research\best.pt"
#
# 安全対策：既存フォルダの強制上書き・設定ファイルの変更・クラウド送信を行わない。
param(
    [string]$ModelPath = ""
)

$ErrorActionPreference = "Stop"
$owner = "t21j075dz-alt"
$homeFolder = $env:USERPROFILE
$projects = @(
    @{ Name = "管理者アプリ"; Repository = "parking-guide-admin"; Folder = "parking-guide-admin" },
    @{ Name = "ユーザーアプリ"; Repository = "parking-guide-user"; Folder = "parking-guide-user" },
    @{ Name = "YOLO研究プログラム"; Repository = "parking-vision-research"; Folder = "parking-vision" }
)

Write-Host ""
Write-Host "===== 卒業研究 / 研究室PC 初期セットアップ ====="
Write-Host "保存先: $homeFolder"
Write-Host "GitHubにない動画・モデル・カメラ設定は別途移行します。"
Write-Host "データベースの新規作成とライブ共有は行いません。"
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Gitが見つかりません。Git for Windowsをインストールし、PowerShellを開き直してください。"
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py) が見つかりません。Python 3.11または3.12をインストールしてください。"
}

$pythonVersion = $null
foreach ($candidate in @("3.11", "3.12")) {
    try {
        & py "-$candidate" -c "import sys; assert sys.version_info[:2] == tuple(map(int, '$candidate'.split('.')))" *> $null
        if ($LASTEXITCODE -eq 0) {
            $pythonVersion = $candidate
            break
        }
    } catch {
        # 対象バージョンがない場合は次を調べる。
    }
}
if (-not $pythonVersion) {
    throw "Python 3.11/3.12が見つかりません。いずれかをインストールしてください。"
}
Write-Host "[確認] Python $pythonVersion"

foreach ($project in $projects) {
    $folder = Join-Path $homeFolder $project.Folder
    $remote = "https://github.com/$owner/$($project.Repository).git"
    Write-Host ""
    Write-Host "[取得] $($project.Name): $folder"

    if (-not (Test-Path -LiteralPath $folder)) {
        & git clone $remote $folder
        if ($LASTEXITCODE -ne 0) {
            throw "$($project.Name)を取得できませんでした。GitHubログインとリポジトリへのアクセス権を確認してください。"
        }
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $folder ".git") -PathType Container)) {
            throw "$folder はGit管理されていません。既存のデータを保護するため停止しました。"
        }
        $actualRemote = (& git -C $folder remote get-url origin | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $actualRemote -notin @(
            $remote,
            "https://github.com/$owner/$($project.Repository)",
            "git@github.com:$owner/$($project.Repository).git"
        )) {
            throw "$folder のGitHub接続先が想定と異なります。上書きせず停止しました: $actualRemote"
        }
        $changes = (& git -C $folder status --porcelain | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $changes) {
            throw "$folder に未保存のローカル変更があります。変更を確認してから再実行してください。"
        }
        & git -C $folder pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            throw "$($project.Name)の安全な更新に失敗しました。上書きは行っていません。"
        }
    }
}

$researchFolder = Join-Path $homeFolder "parking-vision"
$adminFolder = Join-Path $homeFolder "parking-guide-admin"
$venvFolder = Join-Path $researchFolder ".venv-cpu"
$venvPython = Join-Path $venvFolder "Scripts\python.exe"
$requirements = Join-Path $adminFolder "parking-vision\requirements.txt"

if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "依存ライブラリ一覧がありません: $requirements"
}

Write-Host ""
Write-Host "[準備] YOLO用Python仮想環境"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    & py "-$pythonVersion" -m venv $venvFolder
    if ($LASTEXITCODE -ne 0) {
        throw "Python仮想環境の作成に失敗しました。"
    }
} else {
    Write-Host "既存の仮想環境を再利用します。"
}

& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "必要なPythonライブラリをインストールできませんでした。ネットワーク・容量を確認してください。"
}
& $venvPython -c "import sys, cv2, ultralytics, torch; print('Python:', sys.version.split()[0]); print('OpenCV:', cv2.__version__); print('Ultralytics:', ultralytics.__version__); print('CUDA:', torch.cuda.is_available())"
if ($LASTEXITCODE -ne 0) {
    throw "YOLO用ライブラリの動作確認に失敗しました。"
}

$modelDestination = Join-Path $researchFolder "weights\visdrone_finetune_best.pt"
if ($ModelPath) {
    $sourcePath = (Resolve-Path -LiteralPath $ModelPath -ErrorAction Stop).Path
    if ([IO.Path]::GetExtension($sourcePath).ToLowerInvariant() -ne ".pt") {
        throw "学習済みモデルは.ptファイルを指定してください。"
    }
    $modelFolder = Split-Path -Parent $modelDestination
    if (-not (Test-Path -LiteralPath $modelFolder)) {
        New-Item -ItemType Directory -Path $modelFolder | Out-Null
    }
    if (Test-Path -LiteralPath $modelDestination -PathType Leaf) {
        $same = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -eq
                (Get-FileHash -LiteralPath $modelDestination -Algorithm SHA256).Hash
        if (-not $same) {
            throw "既存モデルと内容が異なります。既存ファイルを上書きせず停止しました。"
        }
        Write-Host "[確認] 学習済みモデルは移行済みです。"
    } else {
        Copy-Item -LiteralPath $sourcePath -Destination $modelDestination
        $same = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -eq
                (Get-FileHash -LiteralPath $modelDestination -Algorithm SHA256).Hash
        if (-not $same) {
            throw "モデルのコピー後チェックに失敗しました。"
        }
        Write-Host "[コピー完了] $modelDestination"
    }
}

Write-Host ""
Write-Host "========== セットアップの確認結果 =========="
Write-Host "[OK] GitHubの3プログラムを取得・更新しました。"
Write-Host "[OK] Python・YOLOの基本動作を確認しました。"
if (Test-Path -LiteralPath $modelDestination -PathType Leaf) {
    Write-Host "[OK] 学習済みモデルが見つかりました。"
} else {
    Write-Host "[要対応] best.ptを研究室PCへコピーしてください。"
    Write-Host "再実行例: .\setup_lab_pc.ps1 -ModelPath 'E:\research\best.pt'"
}
foreach ($fileName in @("config.json", "config_video_demo.json", "config_camo.json")) {
    $path = Join-Path $adminFolder "parking-vision\$fileName"
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Host "[確認] $fileName は存在します。モデルの絶対パス・カメラ番号・区画座標を確認してください。"
    } else {
        Write-Host "[要対応] $fileName は未配置です（利用するモードに応じて移行）。"
    }
}
Write-Host ""
Write-Host "次は同じリポジトリにある LAB-PC-SETUP.md を読んでください。"
Write-Host "録画動画・実験CSVは自動でコピーしていません。"
Write-Host "クラウド送信やカメラ公開は開始していません。"
