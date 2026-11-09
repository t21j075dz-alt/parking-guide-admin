# 2026-11-09 録画実験：再駐車後も車両が「出庫中」と表示される問題

## 確認した診断記録

2026-11-09の約600秒の録画診断CSVで、安定ID1の車は約495.6秒に
1番区画が「停車中」となっても車両状態がexitingのままでした。
約587秒の3番区画への再駐車も同様でした。

録画用の駐車区画状態と車両セッションの状態が独立していたのが原因です。
区画はRecordedParkingStateMachineの実映像接地判定を使用しますが、
VehicleTrackerは別のzone_candidate投票を使用し、
今回は録画映像で実際に停車していてもzone_candidateが欠損していました。

## 修正の内容

reconcile_video_reparking.pyを追加し、monitor.pyの録画判定直後に実行。
録画区画のstoppedと同一安定ID・現在フレームの停車検知が一致したときだけ
車両のexitingをparkedへ変更します。前の車両IDは維持します。

安全条件：
- 現在のフレームで検出された監視対象内の車であり、検出確認済み・信頼度0.35以上
- 録画用の区画がstoppedで、その所有車両IDが同じID
- 現在の車両自身のdemo_zoneとdemo_stoppedが同じ区画を裏付ける
- 対象車両はexiting、ほかの確定駐車車が同じ区画を占有していない
- 重複検出、複数台の区画取り合い、古い記録だけの場合は再駐車とみなさない

同じ区画へ戻る場合も、別の区画へ駐車する場合も対象です。
実カメラの判定、YOLOの重み、Supabase、駐車区画の占有判定は変更しません。

## 再確認手順（Windows PowerShell 5.1）

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision

$video = "G:\parking-testmovie\20261029_165836_579397\映像_001.mp4"
$model = ".\runs\unified_training\vehicle_lighting_auto_v1\weights\last.pt"

Test-Path $video
Test-Path $model

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video $video -SegmentationTracking -SegmentationQuality High -SegmentationModel $model -SegmentationImageSize 960
~~~

Test-Pathが両方Trueのときだけ実行。
録画区画の位置確認が求められたら、白線との位置が一致するか確認します。
約600秒を最後まで再生し、ループしたらQで終了してください。

重点観測：
- 約495～497秒：1番区画stoppedと同時に安定ID1がparkedへ戻るか
- 約541～543秒：1番から出庫して車両がexitingになるか
- 約587～589秒：3番区画stoppedと同時に安定ID1がparkedへ戻るか
- 約595～597秒：3番区画の最終出庫とID継続が保たれるか
- 4番区画の誤occupiedがないか

駐車区画_判定診断.csv、区画状態の変化.csv、YOLO判定_001.mp4を照合。
新しい実動画による実測確認はまだ実施していません。

## 回帰テスト

tests/test_reconcile_video_reparking.pyに、
495.6秒・587秒の再駐車、同じ区画への戻り、移動中・不明・低信頼度・
他車ID・複数台の誤結合拒否、録画区画状態機械との結合テストを追加しました。
