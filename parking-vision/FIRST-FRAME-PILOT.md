# 1枚目だけの試験学習＋コーンなどの障害物ラベル付け

この手順は道の駅日光の `vehicle_mask_sessions/nikko_01` に
**1枚目50輪郭、2～8枚目は一部の移動車のみ**を付けた状態向けです。
元動画・ラベルは研究用PCに保存し、GitHubには上げません。

> **重要**: 1枚だけの学習は「学習処理が動くか確認する試験」です。
> 別撮影の検証画像がないため、精度・汎化性能の向上は検証できません。
> 既存の `best.pt` / Supabase / カメラ設定 / ユーザーアプリは上書きしません。

## 0. 研究PCのPowerShell

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
$researchPython = "$env:USERPROFILE\parking-yolo-home\.venv-gpu\Scripts\python.exe"
& $researchPython -c "import cv2, torch, ultralytics; print('CUDA:', torch.cuda.is_available())"
```

OpenCVは既存の研究用Pythonに導入済み。GPUが使えなくてもCPUで
実行できるが処理が遅い可能性がある。研究用PCのモデルパスを確認する。

## 1. 車体輪郭1枚を別データセットにコピー

```powershell
& $researchPython .\first_frame_pilot.py prepare-seg --session ".\vehicle_mask_sessions\nikko_01" --output ".\vehicle_mask_dataset\nikko_firstframe_pilot"
```

選択するのは `annotation_manifest.csv` の最も早いフレーム1枚だけ。
元の画像とラベルは変更しない。出力には人が手動で囲った**1枚目の50件**
のみが入り、他の7枚の不完全ラベルは除外される。

元画像のSHA256と動画のSHA256、ラベル件数を
`pilot_metadata.json` に記録する。ラベルの位置・クラスID・面積は
`vehicle_mask_dataset.py` の既存検証を再利用。

`dataset.yaml` の `val: images/train` はUltralyticsが要求する
**設定書式のためだけの仮参照**。検証画像が存在することを意味しない。
後述の訓練処理は `val=False` を設定する。
ログ内に値が出ても、それは未使用動画での精度ではない。

## 2. YOLO11s-segで小規模な試験学習

```powershell
& $researchPython .\first_frame_pilot.py train --data ".\vehicle_mask_dataset\nikko_firstframe_pilot\dataset.yaml" --model "yolo11s-seg.pt" --epochs 20 --imgsz 960 --device auto --name "nikko_firstframe_pilot"
```

- 初回はモデルをダウンロードすることがある（ネット接続が必要）。
- バッチ1、検証無効、強いMosaic / MixUp / Copy-Pasteなし。
- 重みの出力先は原則 `parking-vision/runs/vehicle_segmentation/nikko_firstframe_pilot/weights/last.pt`。
- 出力済み実験名は上書きしないため、再実行時は `--name nikko_firstframe_pilot_v2` などに変える。
- GPUメモリ不足なら `--imgsz 640` に下げる。
- **この試験モデルを本番の `vehicle_model` や `segmentation_model` に指定しない**。
- YOLO11-segのCOCO80のクラス番号は車=2、二輪=3、バス=5、トラック=7。VisDrone独自10クラスの `best.pt` と混ぜない。

## 3. 同じ1枚目でコーン・障害物をラベル付けする

`first_frame_pilot.py prepare-obstacles` は画像のみコピーし、
車体輪郭の50個の正解ラベルは**障害物用に引き継がない**。

```powershell
& $researchPython .\first_frame_pilot.py prepare-obstacles --session ".\vehicle_mask_sessions\nikko_01" --output ".\obstacle_training_sessions\nikko_firstframe"
New-Item -ItemType Directory -Force ".\obstacle_training_sessions\independent_val_pending" | Out-Null
& $researchPython .\label_obstacles.py --images ".\obstacle_training_sessions\nikko_firstframe" --validation-images ".\obstacle_training_sessions\independent_val_pending" --dataset ".\dataset\obstacles_nikko_pilot"
```

既存のマウス操作で各物体を**四角い枠**で囲む。
既存5クラスは次のとおり：

1. カラーコーン（traffic_cone）
2. ショッピングカート（shopping_cart）
3. バリケード（barrier）
4. 車止め・ポール（bollard）
5. その他の障害物（obstacle）

写真にこれらの実物がない場合は勝手に枠を作らない。
実物が0件なら確認済みの**負例**として保存できるが、
**障害物を認識できるモデルの学習には正例の写真が必要**。
車両はこの障害物専用データセットのクラスではない。

`independent_val_pending` は今は空でよい。これにより1枚目を
学習側へ置く。**このままtrain_obstacles.pyは実行しない**。
そのコマンドはtrainとval両方に正解データを要求するため、
別日に撮影したコーン等の写真を検証用に用意し、ラベル付けする。

## 4. 本格学習への移行条件

- 車体輪郭：新しい独立した撮影セッションでtrain/val/testを分け、
  `VEHICLE-MASK-TRAINING.md` の通常の学習フローに進む。
- 障害物：実際のコーン、カート、バリケード等が写った画像を撮影し、
  別の撮影日に得た検証データを登録後、
  `train_obstacles.py` で別のYOLO検出モデルを学習する。
- 評価：未使用の映像でmask mAP、車両の追跡ID、誤った「空き」案内、
  障害物の検出漏れを確認する。**1枚目の訓練損失は現場での性能を示さない**。
- 障害物モデルの実運用接続は別途検証し、
  既存ユーザー画面やSupabaseには無断で反映しない。

## 参考（公式資料）

- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/modes/train/
- https://docs.ultralytics.com/modes/val/
- https://academy.ultralytics.com/ja/courses/train-your-first-yolo/write-the-data-yaml
