# YOLO認識状況：ライブカメラと追加学習モデルの確認

現在のカメラ判定と、追加学習した複数モデルによる静止画・録画の推論結果を、研究PCだけで比較します。Supabase・本番設定は変更しません。

## 1. 現在のカメラと駐車枠の状態

PowerShell:

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
$researchPython = "$env:USERPROFILE\parking-yolo-home\.venv-gpu\Scripts\python.exe"
& $researchPython .\monitor.py --config ".\config.json" --preview --dry-run
~~~

車両の検出枠、追跡ID、障害物、空き・駐車中・確認中などの駐車枠状態を確認できます。--dry-runでクラウド送信なし。現行設定のモデルで表示します。

## 2. 手元の重みが完成しているか確認

~~~powershell
& $researchPython .\recognition_status_preview.py --status-only
~~~

current（config.jsonのモデル）、vehicle_mask、obstacle、vehicle_boxを検査。
見つからない重みはローカル重みなしと表示して、適当な事前学習モデルに置き換えません。

## 3. 241枚の写真から12枚を分散抽出して比較

~~~powershell
& $researchPython .\recognition_status_preview.py --samples 12
~~~

写真はannotation_workspaces/photos_242/source.jsonから参照。
元画像、現行モデル、学習済み車体輪郭、障害物、車両の矩形検出を同時表示。
どのキーでも次の写真、Qで終了。
出力：runs/recognition_status/日時/recognition_*.jpg と recognition_counts.csv。

画像は学習に使った写真なので、見た目の確認のみ。
精度の検証には未使用の別撮影の録画が必要です。

## 4. 未使用動画を比較（推奨）

~~~powershell
& $researchPython .\recognition_status_preview.py --video "G:\研究動画\20261029_165836_579397\映像_001.mp4" --samples 12 --interval 5
~~~

動画パスは以前使用した例で、研究PCに無ければ実在するMP4に変更。
5秒ごと最大12枚だけ推論します。連続追跡・区画の判定はmonitory.pyではなくmonitor.pyのプレビューで確認。
画面表示なしで画像とCSVだけ保存したい場合は --save-only を指定。

## 5. 学習済みのモデルの重みを明示指定

~~~powershell
& $researchPython .\recognition_status_preview.py --vehicle-mask ".\runs\unified_training\vehicle_lighting_auto_v1\weights\last.pt" --obstacle ".\runs\unified_training\obstacle_auto_v1\weights\last.pt" --vehicle-box ".\runs\unified_training\vehicle_box_auto_v1\weights\last.pt" --samples 12
~~~

上記のパスに重みが無いときはエラー。--status-onlyで先に確認。
学習状況を推測で補いません。
Ultralytics Results.plotで検出枠・マスク・確信度を可視化します。

## 公式資料

- https://docs.ultralytics.com/modes/predict/
- https://docs.ultralytics.com/reference/engine/results/
