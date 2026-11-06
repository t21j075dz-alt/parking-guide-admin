# 車両の輪郭と障害物を一つの画面で登録（242枚対応）

車両は**輪郭ポリゴン**、コーンなどは**四角い検出枠**として、
同じ画像に登録できます。学習モデル・正解ラベルのファイルは別々です。
元画像、従来のbest.pt、Supabase、利用者アプリは変更しません。

## 起動

PowerShell 5.1で以下を実行：

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
$researchPython = "$env:USERPROFILE\parking-yolo-home\.venv-gpu\Scripts\python.exe"
& $researchPython .\unified_annotator.py
~~~

写真フォルダの選択画面が開くので、以前撮影した242枚の
**myparkingphoto_20261022 の original フォルダ**を選んでください。
旧PCの例は C:\Users\Owner\Desktop\parking-yolo-starter\myparkingphoto_20261022\original ですが、
今のPCに同じ場所があるとは限りません。画面・PowerShellに
「写真一覧 242枚」と出るか確かめてください。
または parking-vision 内の「車両と障害物_まとめて登録.cmd」をダブルクリック。

## 操作方法

- **車両の輪郭**：左クリックで車体外周に点を置き、Enterで1台確定。
  その写真に映る学習対象の車は原則すべて囲んでください。
- **コーン・障害物**：種類を選んでマウスでドラッグして四角く囲む。
  コーン、カート、バリケード、車止め・ポール、その他障害物の5種。
- **確認して保存**：現在の種類を確認済みにし、未確認のもう一種類へ進む。
  両方保存済みなら次の未登録画像へ。
- **対象なしとして保存**：その種類が本当に写っていない時のみ押す。
  空のラベルは確認済みの負例、ファイルなしは未確認として区別する。
- **次の画像（未登録は保留）**：その画像を未確認のまま残す。
- **前の画像／戻す／拡大・縮小**：修正や遠方車両への対応。
  Ctrl+Sで保存、Ctrl+Zで戻す、Escで未確定点を消す。

途中で終了しても、同じ元フォルダから再開できます。
保存先は parking-vision/annotation_workspaces/photos_242/labels 以下の
vehicle と obstacle に分かれます。

以前YOLO26等で推論して得た自動検出枠は、**人の正解ラベルとして流用しません**。
昔の動画フレームのannotation_manifest.csvに対応した手動輪郭は、
画面内の候補として表示できますが、利用者が再確認して保存するまで未確認扱いです。

## 242枚が登録できたら学習データを書き出す

~~~powershell
& $researchPython .\unified_annotator.py export --mode vehicle --train-workspace ".\annotation_workspaces\photos_242" --output ".\reviewed_photo_datasets\vehicle_242_pilot" --train-only
& $researchPython .\unified_annotator.py export --mode obstacle --train-workspace ".\annotation_workspaces\photos_242" --output ".\reviewed_photo_datasets\obstacle_242_pilot" --train-only
~~~

未確認の画像や不正なラベル、同一画像の重複を検出したら停止します。
車両学習はCOCO80クラスID 2,3,5,7、障害物は5独自クラスID 0～4。
**二つのYOLOモデルの重みは混ぜません。**

## 242枚を使った試験学習（ラベル完成後）

~~~powershell
& $researchPython .\train_reviewed_photos.py --task vehicle --data ".\reviewed_photo_datasets\vehicle_242_pilot\dataset.yaml" --model "yolo11s-seg.pt" --epochs 40 --imgsz 960 --batch 2 --device auto --name "vehicle_242_pilot" --accept-train-only
& $researchPython .\train_reviewed_photos.py --task obstacle --data ".\reviewed_photo_datasets\obstacle_242_pilot\dataset.yaml" --model "yolo11n.pt" --epochs 40 --imgsz 960 --batch 2 --device auto --name "obstacle_242_pilot" --accept-train-only
~~~

**独立した検証用画像がないため、上記は試験学習のみ。**
設定上のval: images/trainは書式上の仮参照で、試験ではval=Falseにします。
実験出力は parking-vision/runs/unified_training に保存します。
本番への自動反映はしません。

本格評価は別の日・別撮影セッションの写真を新しいワークスペースで
ラベル付けし、exportに --val-workspace と必要なら --test-workspace を
追加してから行います。連写をランダムに分割しても独立検証にはなりません。

## 根拠・仕様
- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/datasets/detect/
- https://docs.ultralytics.com/modes/train/
- https://docs.ultralytics.com/modes/val/
