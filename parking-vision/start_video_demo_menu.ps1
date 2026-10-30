# Windows PowerShell 5.1; same numeric menu as the original recording demo.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "================================================"
Write-Host "録画動画をYOLOでループ判定し、案内へ反映する研究実演"
Write-Host "================================================"
Write-Host ""
Write-Host "1. PC内だけで確認（クラウド送信しない）"
Write-Host "2. 録画実演専用のユーザーアプリへ共有（Qキーで停止）"
Write-Host ""
$choice = (Read-Host "番号を選択してください（1/2）").Trim()
try {
    if ($choice -eq "1") {
        & (Join-Path $PSScriptRoot "start_video_demo.ps1")
    } elseif ($choice -eq "2") {
        & (Join-Path $PSScriptRoot "start_video_demo.ps1") -Share
    } else {
        Write-Host "【中止】1 または 2 を入力してください。"
    }
} catch {
    Write-Host ("【エラー】" + $_.Exception.Message) -ForegroundColor Red
} finally {
    Write-Host ""
    [void](Read-Host "終了するには Enter を押してください")
}
