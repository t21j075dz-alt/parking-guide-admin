# 2026-11-09 追加の不具合修正と確認手順

## 根拠となる診断結果

- 駐車区画_判定診断(20261109-090301).csv: 299行。parkedだが安定区画が空欄の記録24件。
- 車両輪郭_比較診断(20261109-090305).csv: 5,953行。geometry conflict 78件、短時間の別ID2が10件。
- YOLO判定_001(20261109-090312).mp4 / YOLO判定_002(2).mp4: 車両と区画の説明文字が重なる場面を確認。

## 修正済み

1. 録画動画の6区画の長い状態ラベルを車両の上から取り除き、動画の下に専用表示欄を作成。映像の区画内表示は短い番号へ変更。リアルタイムの通常表示には従来の表示を保持。
2. 監視対象外・未検証の車がID2など確定済みの車両のように表示されないよう、画面表示だけID:UNVERIFIEDに変更。診断に必要な検出枠は残す。
3. CSVで従来の『安定区画』が空欄のままでも、録画用に停止が確認された区画を新設の『確定駐車区画』に明示し、別列『駐車区画確定の根拠』で出所を区別。
4. CSV『使用した区画根拠』に実際のfusionの判定（agreement/mask-temporal/conflictなど）を記録。以前のbottom-footprint固定表示を修正。
5. 同一車両の再駐車確定イベントは2秒ごとの通常サンプリングを待たずCSVへ記録。

## 引き続き検証が必要

- 78件の区画判定不一致は、境界近傍で検出枠と輪郭が異なることを示すが、空き・占有の誤判定78件という意味ではない。片方に強制割当てしない。
- 別ID2の10件は追加された一時検出。今回の変更は誤解を招く画面表示の修正で、YOLOモデルの誤認識自体を消したわけではない。
- 人物IDの未確定は確認待ちという仕様の場合があるため、今回は誤って全員にIDを強制割当てしない。
- 車両状態と区画状態の1～2秒の差は安全側の確認待ち時間による場合があるため、無理に同期させない。

## Windowsの動画再確認

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

両方Trueであることを確認してください。動画に増えた下部欄と新しいCSV列を点検し、実映像を一周最後まで見てQで終了。

既存の駐車区画状態機械、Supabase、ユーザーアプリ、本番用重みは変更していません。
