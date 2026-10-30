# Windows PowerShell 5.1 drag-and-drop video demo launcher.
# Nothing is uploaded by selecting a file.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$script:video = ""
$script:running = $null
$script:extensions = @(".mp4", ".avi", ".mov", ".mkv", ".webm")
$script:config = Join-Path $PSScriptRoot "config_video_demo.json"
$script:python = Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"

function Make-Label([string]$value, [int]$x, [int]$y, [int]$w, [int]$h, [float]$size, [bool]$bold = $false) {
    $c = New-Object System.Windows.Forms.Label
    $c.Text = $value
    $c.Location = New-Object System.Drawing.Point($x, $y)
    $c.Size = New-Object System.Drawing.Size($w, $h)
    $style = if ($bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
    $c.Font = New-Object System.Drawing.Font("Yu Gothic UI", $size, $style)
    return $c
}
function Make-Button([string]$value, [int]$x, [int]$y, [int]$w, [int]$h) {
    $c = New-Object System.Windows.Forms.Button
    $c.Text = $value
    $c.Location = New-Object System.Drawing.Point($x, $y)
    $c.Size = New-Object System.Drawing.Size($w, $h)
    $c.Font = New-Object System.Drawing.Font("Yu Gothic UI", 10)
    return $c
}
function Warn([string]$msg) {
    [void][System.Windows.Forms.MessageBox]::Show($msg, "録画YOLO実験", "OK", "Warning")
}
function Pick-Video([string]$candidate) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf) -or
        [IO.Path]::GetExtension($candidate).ToLowerInvariant() -notin $script:extensions) {
        Warn "対応している動画ファイルを1本選択してください。MP4 / AVI / MOV / MKV / WEBM"
        return
    }
    $script:video = (Resolve-Path -LiteralPath $candidate).Path
    $pathDisplay.Text = $script:video
    $dropBox.Text = "選択済み：" + [IO.Path]::GetFileName($script:video) +
        [Environment]::NewLine + "別の動画もドロップできます"
    $status.Text = "動画が選択されました。録画用区画が一致するか確認してください。"
}
function Get-CheckedConfig {
    if (-not (Test-Path -LiteralPath $script:config -PathType Leaf)) {
        throw "録画用設定が見つかりません。先にregenerate_lab_assets.pyを実行してください。"
    }
    $settings = Get-Content -LiteralPath $script:config -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$settings.facility_id -ne "home-video-demo-001") {
        throw "録画実験専用の施設IDではありません。別の施設に録画を公開できません。"
    }
    $zones = @($settings.space_zones.PSObject.Properties)
    $expected = @("space_001","space_002","space_003","space_004","space_005","space_006")
    $actual = @($zones | ForEach-Object { $_.Name })
    if ($zones.Count -ne 6 -or @($expected | Where-Object { $_ -notin $actual }).Count -gt 0) {
        throw "録画用の6区画が未登録です。先に『登録済み区画を取り込む』で動画と照合してください。"
    }
    if (-not (Test-Path -LiteralPath ([string]$settings.vehicle_model) -PathType Leaf)) {
        throw "録画用設定の学習済みモデルが見つかりません。vehicle_modelのパスを確認してください。"
    }
    return $settings
}
function Run-Experiment([bool]$share) {
    if (-not $script:video) { Warn "動画をドラッグ＆ドロップしてください。"; return }
    if ($script:running -and -not $script:running.HasExited) {
        Warn "実験を二重起動できません。映像の画面でQを押し、実験のウィンドウを閉じてください。"
        return
    }
    try { $null = Get-CheckedConfig }
    catch { Warn ([string]$_.Exception.Message); return }
    if ($share) {
        $message = "過去の録画によるYOLO実演です。実際の現在の空きではありません。" +
            [Environment]::NewLine + [Environment]::NewLine +
            "管理者の認証後、録画専用施設だけに状態を送信します。ユーザーアプリと連携します。" +
            [Environment]::NewLine + "共有を開始しますか？"
        $confirm = [System.Windows.Forms.MessageBox]::Show(
            $message, "録画の共有確認", [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Warning)
        if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    }
    try {
        $runner = Join-Path $PSScriptRoot "video_demo_run_window.ps1"
        if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw "起動ファイルがありません。" }
        $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $runner +
            '" -Video "' + $script:video + '"'
        if ($share) { $args += " -Share" }
        $script:running = Start-Process powershell.exe -ArgumentList $args -PassThru
        $offline.Enabled = $false
        $publish.Enabled = $false
        $status.Text = "別ウィンドウで開始。映像のS=区画確認、Q=中止。共有時は管理者ログインが必要です。"
    } catch { Warn ([string]$_.Exception.Message) }
}
function Check-Share {
    try {
        $settings = Get-CheckedConfig
        $url = [string]$settings.supabase_url
        $key = [string]$settings.publishable_key
        if ($url -notmatch '^https://[a-z0-9-]+\.supabase\.co$' -or
            -not $key.StartsWith("sb_publishable_")) {
            throw "クラウド接続先を確認してください。"
        }
        $head = @{ apikey = $key }
        $uri = $url.TrimEnd("/") + "/rest/v1/parking_live_visibility?facility_id=eq.home-video-demo-001&select=is_published&limit=1"
        $list = @(Invoke-RestMethod -Method Get -Uri $uri -Headers $head -TimeoutSec 8)
        if ($list.Count -eq 0 -or $list[0].is_published -ne $true) {
            $status.Text = "録画実演の共有：OFF（ユーザーアプリに現在の判定は出していません）"
            return
        }
        $uri = $url.TrimEnd("/") + "/rest/v1/parking_live_status?facility_id=eq.home-video-demo-001&select=space_uid,source,checked_at"
        $rows = @(Invoke-RestMethod -Method Get -Uri $uri -Headers $head -TimeoutSec 8)
        $now = [DateTimeOffset]::UtcNow
        $valid = @($rows | Where-Object {
            if ($_.source -ne "recorded_video_demo") { return $false }
            try {
                $age = ($now - [DateTimeOffset]::Parse([string]$_.checked_at)).TotalSeconds
                return ($age -ge -5 -and $age -le 20)
            } catch { return $false }
        })
        if ($valid.Count -gt 0) {
            $status.Text = "共有中：新しい録画判定 " + $valid.Count + "区画 / ユーザーアプリで確認できます"
        } else {
            $status.Text = "共有設定はONですが、20秒以内の録画判定がありません。状態は未確認です。"
        }
    } catch {
        $status.Text = "共有状態を確認できません。通信・設定・アクセス権限を確認してください。"
        Warn ([string]$_.Exception.Message)
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "卒業研究：録画YOLOとユーザーアプリ連携"
$form.ClientSize = New-Object System.Drawing.Size(790, 550)
$form.StartPosition = "CenterScreen"
$form.BackColor = [System.Drawing.Color]::White
$form.Font = New-Object System.Drawing.Font("Yu Gothic UI", 10)

$form.Controls.Add((Make-Label "録画YOLO実験" 24 18 735 40 19 $true))
$form.Controls.Add((Make-Label "動画をドラッグ＆ドロップ。録画専用駐車場の判定をユーザーアプリに連携できます。" 24 67 735 45 10))

$dropBox = Make-Label ("ここに動画をドラッグ＆ドロップ" + [Environment]::NewLine +
    "MP4 / AVI / MOV / MKV / WEBM") 24 116 740 108 13 $true
$dropBox.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$dropBox.BackColor = [System.Drawing.Color]::FromArgb(233, 243, 255)
$dropBox.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$dropBox.AllowDrop = $true
$form.Controls.Add($dropBox)
$form.AllowDrop = $true

$dragEnter = {
    param($sender, $e)
    $e.Effect = [System.Windows.Forms.DragDropEffects]::None
    if ($e.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) {
        $items = @($e.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop))
        if ($items.Count -eq 1 -and
            [IO.Path]::GetExtension([string]$items[0]).ToLowerInvariant() -in $script:extensions) {
            $e.Effect = [System.Windows.Forms.DragDropEffects]::Copy
        }
    }
}
$dropHandler = {
    param($sender, $e)
    $items = @($e.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop))
    if ($items.Count -eq 1) { Pick-Video ([string]$items[0]) }
}
$dropBox.add_DragEnter($dragEnter)
$dropBox.add_DragDrop($dropHandler)
$form.add_DragEnter($dragEnter)
$form.add_DragDrop($dropHandler)

$pathDisplay = New-Object System.Windows.Forms.TextBox
$pathDisplay.Location = New-Object System.Drawing.Point(24, 244)
$pathDisplay.Size = New-Object System.Drawing.Size(600, 27)
$pathDisplay.ReadOnly = $true
$pathDisplay.Text = "動画が選択されていません"
$form.Controls.Add($pathDisplay)

$browse = Make-Button "ファイルを選ぶ" 636 241 128 34
$browse.Add_Click({
    $fileDialog = New-Object System.Windows.Forms.OpenFileDialog
    $fileDialog.Filter = "動画|*.mp4;*.avi;*.mov;*.mkv;*.webm|すべてのファイル|*.*"
    if ($fileDialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        Pick-Video $fileDialog.FileName
    }
    $fileDialog.Dispose()
})
$form.Controls.Add($browse)

$zones = Make-Button "登録済みの6区画を取り込む・照合する" 24 295 470 41
$zones.Add_Click({
    if (-not $script:video) { Warn "先に動画を選んでください。"; return }
    $choose = New-Object System.Windows.Forms.OpenFileDialog
    $choose.Title = "6区画が登録済みのカメラ設定を選択"
    $choose.Filter = "JSON設定|*.json"
    foreach ($candidate in @(
        (Join-Path $PSScriptRoot "config_usb_original.json"),
        (Join-Path $PSScriptRoot "config_laptop_original.json"),
        (Join-Path $PSScriptRoot "config_from_laptop.json"),
        "D:\config.json"
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $choose.InitialDirectory = Split-Path $candidate -Parent
            $choose.FileName = Split-Path $candidate -Leaf
            break
        }
    }
    if ($choose.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        $choose.Dispose(); return
    }
    $source = $choose.FileName
    $choose.Dispose()
    $zoneRunner = Join-Path $PSScriptRoot "video_demo_zone_window.ps1"
    $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $zoneRunner +
        '" -SourceConfig "' + $source + '" -Video "' + $script:video + '"'
    try {
        $null = Start-Process powershell.exe -ArgumentList $args -PassThru
        $status.Text = "区画確認を開始。映像の区画が一致していればS、違えばQを押してください。"
    } catch { Warn ([string]$_.Exception.Message) }
})
$form.Controls.Add($zones)

$calibrate = Make-Button "動画の画角で6区画を新規登録" 501 295 263 41
$calibrate.Add_Click({
    if (-not $script:video) { Warn "先に動画を選んでください。"; return }
    $runner = Join-Path $PSScriptRoot "video_demo_calibrate_window.ps1"
    $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $runner +
        '" -Video "' + $script:video + '"'
    try {
        $null = Start-Process powershell.exe -ArgumentList $args -PassThru
        $status.Text = "動画の画角で区画を登録します。4点ずつ指定し、Qで保存してください。"
    } catch { Warn ([string]$_.Exception.Message) }
})
$form.Controls.Add($calibrate)

$offline = Make-Button "PCだけで判定する" 24 365 352 54
$offline.Add_Click({ Run-Experiment $false })
$form.Controls.Add($offline)
$publish = Make-Button "ユーザーアプリと連携して開始" 390 365 374 54
$publish.Add_Click({ Run-Experiment $true })
$form.Controls.Add($publish)

$check = Make-Button "共有の状態を確認" 24 432 185 37
$check.Add_Click({ Check-Share })
$form.Controls.Add($check)
$app = Make-Button "ユーザーアプリを開く" 221 432 205 37
$app.Add_Click({ Start-Process "https://t21j075dz-alt.github.io/parking-guide-user/" })
$form.Controls.Add($app)

$status = Make-Label "録画専用施設：home-video-demo-001。実際の駐車場の現在の空きではありません。" 24 477 744 29 9
$form.Controls.Add($status)
$form.Controls.Add((Make-Label "停止：判定映像の画面でQ。終了時は共有OFF。アプリでは「実験用駐車場（自宅駐車場録画用）」を選択。" 24 507 744 26 8))

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 1500
$timer.Add_Tick({
    if ($script:running -and $script:running.HasExited) {
        $script:running = $null
        $offline.Enabled = $true
        $publish.Enabled = $true
        $status.Text = "実験ウィンドウを閉じました。必要なら再度開始できます。"
    }
})
$timer.Start()
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })
[void]$form.ShowDialog()
$form.Dispose()
