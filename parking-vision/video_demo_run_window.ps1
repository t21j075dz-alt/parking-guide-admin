param(
    [Parameter(Mandatory=$true)][string]$Video,
    [switch]$Share
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "========== 録画YOLO：実験の実行 =========="
Write-Host "動画: $Video"
Write-Host "録画専用施設: home-video-demo-001"
if ($Share) {
    Write-Host "共有モードです。次の画面で「録画共有」を入力し、管理者でログインしてください。"
} else {
    Write-Host "ローカル判定モードです。クラウドへの送信は行いません。"
}
Write-Host "映像上の区画を目視確認してSを押してください。違えばQで中止できます。"
try {
    & (Join-Path $PSScriptRoot "start_video_demo.ps1") -Video $Video -Share:$Share
    if ($LASTEXITCODE -ne 0) {
        Write-Host "【注意】判定が正常終了しませんでした。上のエラーを確認してください。"
    }
} catch {
    Write-Host "【エラー】$($_.Exception.Message)" -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "共有していた場合、終了時にOFFへ戻す処理を実行します。"
    Write-Host "【操作】Enterキーでこの画面を閉じてください。"
    [void](Read-Host "Enter")
}
