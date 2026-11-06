# 手作業の追加ラベルなしで自動学習する方法

登録済み241枚、車両893個、障害物346個を再利用します。新しいラベル付けは不要。
車両の輪郭・障害物を自動拡張学習し、車両輪郭から車両検出用の四角枠も自動生成します。
実際の夜間・雨・別角度の写真が増えたわけではなく、精度向上は未検証です。

## PowerShell 5.1: 準備

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
$researchPython = "$env:USERPROFILE\parking-yolo-home\.venv-gpu\Scripts\python.exe"
& $researchPython -c "import torch; print('CUDA:',torch.cuda.is_available()); print('GPU:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
~~~

## 1. 車体輪郭を明るさ・色変化で自動学習

固定カメラに適したlightingプロファイルは、写真内の物体位置を動かさず、
照明と色調だけを毎エポック変化させます。既存の893個の車体マスクを使います。

~~~powershell
& $researchPython .\train_reviewed_photos.py --task vehicle --data ".\reviewed_photo_datasets\vehicle_242_pilot\dataset.yaml" --model "yolo11s-seg.pt" --auto-augment lighting --epochs 40 --imgsz 960 --batch 2 --device auto --name "vehicle_lighting_auto_v1" --accept-train-only
~~~

オプションをparkingにすると、少量の位置・大きさ・左右反転も加えます。
固定カメラの視点を保つ比較実験ではlightingを優先してください。

## 2. 車両の検出枠を自動生成し、別のYOLO detectを学習

人が確認した車体輪郭の外接矩形を計算します。新しい物体の正解は増えません。

~~~powershell
& $researchPython .\derive_vehicle_detection_dataset.py --source ".\reviewed_photo_datasets\vehicle_242_pilot" --output ".\reviewed_photo_datasets\vehicle_detect_auto_v1"
~~~

準備が正常なら241枚・893枠。COCO80の車両クラスID（2,3,5,7）を維持。

~~~powershell
& $researchPython .\train_reviewed_photos.py --task vehicle_detect --data ".\reviewed_photo_datasets\vehicle_detect_auto_v1\dataset.yaml" --model "yolo11n.pt" --auto-augment parking --epochs 40 --imgsz 960 --batch 2 --device auto --name "vehicle_box_auto_v1" --accept-train-only
~~~

この車両専用追加学習によってCOCOの人・自転車等の精度維持は保証されません。
従来の人物検出モデルを置き換えないでください。

## 3. コーン・障害物を自動データ拡張して学習

~~~powershell
& $researchPython .\train_reviewed_photos.py --task obstacle --data ".\reviewed_photo_datasets\obstacle_242_pilot\dataset.yaml" --model "yolo11n.pt" --auto-augment parking --epochs 40 --imgsz 960 --batch 2 --device auto --name "obstacle_auto_v1" --accept-train-only
~~~

障害物346件の内訳は下記コマンドで確認できます。未登録クラスの自動追加はしません。

~~~powershell
& $researchPython .\training_gap_report.py
~~~

## 安全対策

- 3モデルの学習は同時実行せず、上から順番に実行する。
- 既存モデルのbest.pt、config.json、Supabase、アプリ、元写真、手動ラベルは変更しない。
- モデルはparking-vision/runs/unified_trainingの別々の実験フォルダに保存する。
- GPUメモリ不足ならbatch1かimgsz640で再試行、実験名も変更する。
- 重複する学習名は上書きしない。独立したval/testがないためval=False。
- 学習損失の低下だけでは現地の精度が上がったとは断言できない。
- モデルが推測した白線やホイールを正解ラベルとみなして再学習することはしない。
  新規クラスには新たな正解アノテーション、またはレビュー付き仮ラベルが必要。
- 夜間・雨・逆光の実性能は別撮影で必ず確認。カメラ映像の区画IDの自動対応は別課題。

## 公式仕様

- https://docs.ultralytics.com/guides/yolo-data-augmentation/
- https://docs.ultralytics.com/guides/preprocessing-annotated-data/
- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/datasets/detect/
- https://docs.ultralytics.com/modes/train/
