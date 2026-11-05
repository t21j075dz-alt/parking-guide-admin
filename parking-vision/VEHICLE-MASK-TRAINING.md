# 車体輪郭を駐車場映像で追加学習する（YOLO11-seg）

## 研究の目標と現時点

直近のHigh/Maximum比較では、主要車両の検出・追跡・入庫判定に大差が
ありませんでした。また「輪郭取得数」は正しい輪郭の割合ではありません。
次の段階は**実際の車体の外周を人が囲んだ正解データを使い、
輪郭の一致度（mask mAP）を比較すること**です。

**今回追加したもの**は「画像抽出→手動アノテーション→データ検証・
学習/検証/テスト分割→追加学習→既存モデルとの評価」のプログラムです。
**正解輪郭データの作成・GPU学習・精度向上の実測はまだ実施していません。**
実験中のユーザーアプリ・Supabase・稼働中のモデルは変更しません。

Ultralyticsの公式YOLO形式は、画像と同名の.txtに、
1行1物体で「クラス番号 x1 y1 x2 y2...」（0～1の正規化座標、
**最低3点**）を記述します。車体の四角い検出枠は正解輪郭に使用できません。

## 用意する元動画

同じ場所でよいので**別の録画セッションを少なくとも2回、できれば3回以上**
用意してください。カメラの角度・日中と夜間・車体の正面/背面/側面/斜め・
転回・停車・遮蔽・雨天などを含めてください。初回は
「動画A：学習」「動画B：学習途中の検証」「動画C：最終テスト」が理想です。

- **YOLO判定_*.mp4のように輪郭・文字・色が描き込まれた動画は使用しない**。
- 動画内の車体が小さい場合も、車体の見えている外周を囲んでください。
  影・路面・別の車両・見えない部分を含めないでください。
- 人やナンバープレートの情報を無断公開しないでください。
- 車だけならクラス1（キーボード上の1。COCO実データIDは2）。
  他の対象を含む場合は二輪車(キー2: COCO 3)、バス(キー3: COCO 5)、
  トラック(キー4: COCO 7)も漏れなく正解ラベルを付けてください。
  **それ以外のCOCOクラスの検出性能が追加学習後も維持される保証はありません**。

以下は研究用Windows PCのPowerShellを前提とします。
研究用Python仮想環境（ultralytics 8.4.178 / opencv-python導入済み）を
有効にしてから実行してください。以下のG:パスは例です。

### 手順1：元動画を切り出す

```powershell
cd "$env:USERPROFILE\parking-guide-admin\parking-vision"

python .\prepare_vehicle_mask_frames.py --video "G:\研究動画\raw_session_A.mp4" --output ".\vehicle_mask_sessions\session_A"
python .\prepare_vehicle_mask_frames.py --video "G:\研究動画\raw_session_B.mp4" --output ".\vehicle_mask_sessions\session_B"
python .\prepare_vehicle_mask_frames.py --video "G:\研究動画\raw_session_C.mp4" --output ".\vehicle_mask_sessions\session_C"
```

A/B/Cは**独立した元動画**にしてください。同じ元動画の別の部分を
A/B/Cとして指定すると自動で拒否します。抽出ツールは通常30秒ごと、
転回・入庫の148～190秒は2秒ごとに抜き出します。
映像の実態に応じて `--turn-start 60 --turn-end 110` のように変更できます。
`annotation_manifest.csv` に元動画のSHA256を保存します。
認識後の画像ではなく、未加工の元動画を確認するためのファイルです。

### 手順2：車体をマウスで囲む

```powershell
python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_A"
python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_B"
python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_C"
```

- マウス左クリック：車体輪郭の点を追加／右クリック：直前の点を戻す
- `1` 乗用車・`2` 二輪車・`3` バス・`4` トラックを選択
- `Enter`：3点以上の輪郭を確定。1画面に複数の車があればそれぞれ確定
- `U`：点を戻す、`R`：未完成の点または直前の輪郭を削除
- `S`：現在の画像のラベルを保存して次へ
- 車がいない画像：囲わず `S` で空のラベルファイルを作る
- `N`：未保存のままスキップ、`Q`：終了（次回再開可能）

確認した画像のラベルは各セッションの`labels/`内に保存します。
車体の輪郭を正確に囲めない画像は`N`で保留し、
教師データにする前に再確認してください。**自動で偽の正解ラベルは付けません**。

### 手順3：独立した元動画ごとに分割・検証

```powershell
python .\vehicle_mask_dataset.py --train ".\vehicle_mask_sessions\session_A" --val ".\vehicle_mask_sessions\session_B" --test ".\vehicle_mask_sessions\session_C" --output ".\vehicle_mask_dataset\v1"
```

未ラベル画像、不正なクラスID、検出枠形式、座標範囲外、
異常な輪郭面積、同じ元動画や同じ画像の重複を検出すると中止します。
生成される`vehicle_mask_dataset/v1/dataset.yaml`はCOCO80のクラス番号を維持し、
既存YOLO11s-segと新モデルを同じ正解データで公平に評価できます。

**重要：隣接フレームをランダムに学習用とテスト用へ分けません。**
未知の車・未知の撮影時間での性能を確認するため、動画ごとの分割を守ります。

### 手順4：Highモデルを出発点に追加学習

```powershell
python .\train_vehicle_segmentation.py --data ".\vehicle_mask_dataset\v1\dataset.yaml" --model "yolo11s-seg.pt" --epochs 60 --imgsz 960 --batch 4 --device auto --name "parking_vehicle_masks_v1"
```

CUDA GPUが使えないPCではCPU学習となり、処理時間が長くなります。
GPUメモリ不足の場合は`--batch 2`等に下げてください。
Windowsのマルチプロセス問題を避けるため`workers=0`にしています。

モデルは学習実験フォルダに`best.pt`として保存され、
すでに利用しているモデルを上書きしません。
正解データが少ない場合、過学習や別車種の検出性能低下があり得ます。

### 手順5：未使用のテスト動画で精度比較

```powershell
python .\compare_vehicle_segmentation.py --data ".\vehicle_mask_dataset\v1\dataset.yaml" --baseline "yolo11s-seg.pt" --candidate ".\runs\vehicle_segmentation\parking_vehicle_masks_v1\weights\best.pt" --output ".\runs\seg_compare_v1.json"
```

`best.pt`の出力先は学習ログを確認して指定してください。
**両モデルを同じ手動正解輪郭・同じ入力サイズ960で評価**し、
`mask_map50_95`・`mask_map50`・`mask_map75`などをJSONに保存します。
これは**車体輪郭の正解との一致を評価する指標**であり、
駐車区画3番/4番の正答率そのものではありません。

比較が良い場合でも、転回154～169秒、3番区画への入庫170～185秒、
車両IDの継続・夜間・複数台の場面を動画でも確認し、研究用の
`-SegmentationModel "....\best.pt"` で**dry-run**比較してから採用を検討します。
ユーザーアプリへの共有や本番モデルの差し替えは**自動では行いません**。

### コードの自己検証

```powershell
python -m unittest discover -s tests -p "test_vehicle_mask_dataset.py"
```

本コードのラベル形式・データ分割・学習引数等のテストは
**実際にGPU学習が終わった証明ではありません**。

公式資料：
- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/tasks/segment/
- https://docs.ultralytics.com/modes/train/
- https://docs.ultralytics.com/modes/val/
