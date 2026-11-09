# 駐車場YOLO：次の追加学習計画と元動画からの準備

更新日：2026-11-06。これは学習前の実行計画です。**学習済みモデルの精度向上を確認した文書ではありません**。

## 1. 現在のコードから確認した前提

- 稼働中の車両検出：VisDroneを追加学習した独自の10クラス検出器（car / van / truck / bus / pedestrian等）。実機のbest.ptはリポジトリには含まれない。
- 既存の輪郭実験：YOLO11-segによるマスク表示・比較、手動輪郭の正解作成・分割・学習・比較スクリプトが実装済み。**独自の輪郭データを用いたGPU再学習の実績は未確認**。
- 既存の障害物実験：コーン・カート・バリケード・ポール・その他の5クラスのラベル登録・検出学習器は実装済み。追加学習済み重みの存在・精度は未確認。
- BoT-SORTと安定IDは別処理。追跡IDの改善効果を輪郭モデル単体のmAPと混同しない。
- カメラとマップの4点位置合わせは別の幾何処理。車体を検出できるだけでは、画像のどの区画がマップのどのIDかを自動では決められない。

## 2. 学習を始める順番

| 順位 | 学習・データ収集テーマ | アノテーション | 現行の出発点 |
| --- | --- | --- | --- |
| A1 | 正面/背面/側面/斜め、旋回・出入り時の車体輪郭 | 車ごとの見えている外周ポリゴン | YOLO11s-seg、既存輪郭ツール |
| A2 | 薄暗い・夜間・雨・反射・露出変化・影・空車背景 | 実車は車体マスク、実車なしは確認済み空ラベル | A1と同じモデルに統合する。影を独立した「車」クラスにしない |
| A3 | 並んだ車、部分遮蔽、画面端、遠方の車、各車種 | 見えている個体を漏れなく個別にマスク | A1と同じモデルに統合する |
| B1 | カラーコーン、ショッピングカート、バリケード、ポール、その他障害物 | YOLO検出枠 | 既存の障害物専用モデル |
| C1 | 駐車枠の白線・車止め・地面境界 | 別実験の線/領域ラベル（未構築） | 既存の4点合わせ＋検証UIを先に使用 |
| C2 | タイヤ接地点/ホイール位置 | 別実験のキーポイント（未構築） | 車体マスクによる区画判定を先に評価 |
| C3 | 区画番号や表示板 | OCR用の文字・領域ラベル（未構築） | マップの区画IDと視覚的対応点の照合で代替 |

- A1～A3は追加の「クラス」ではなく**状況のバリエーション**。同じcar等のクラスで正しく教師データを付ける。
- セグメンテーションの既存クラスIDはCOCO80の 2=car, 3=motorcycle, 5=bus, 7=truck。COCO80に独立したvanクラスは無い。通常の乗用型ミニバン等はアノテーション基準を統一してcarに含め、配送用の大型バン等は形状・用途を踏まえ先にラベル方針を決める。既存VisDrone10クラスの番号をこのモデルへコピーしない。
- 障害物モデルのクラスIDは 0=traffic_cone, 1=shopping_cart, 2=barrier, 3=bollard, 4=obstacle。車体セグメンテーションとラベル形式が異なるため**学習データも重みも混ぜない**。
- 人、自転車はVisDroneモデルですでに扱うが、対象駐車場で取りこぼす場合のみ実映像データを追加検討する。人の同一性や顔認識は目的に含めない。
- 車体輪郭の下端はタイヤの接地点そのものではない。車体マスクの結果が良くても区画割当てを別途実測評価する。

## 3. 必ず集めたい映像

少なくとも異なる3回の**独立した撮影セッション**を用意する。例として、
A=学習、B=検証、C=最終テスト。完全に同一の元動画を分けたり、
同じ録画の隣接フレームを別分割に振り分けたりしない。

収集対象の優先チェック：
- 日中の空車背景、通常の停車車両
- 前進/後退・右左折・旋回、3番と4番の境界をまたぐ時
- 2台が重なる場面、車が画面端に一部だけ映る場面
- 夜間・白飛び・濡れた地面・車体への反射、影だけの場面
- 軽/普通/ミニバン/トラック等の車種、車体色の違い
- 空区画にコーン・カートがある/ない状態
- 映像上は車があるのに判定が「空き」になった時、逆に空車なのに車を誤検出した時

最初の試行用の**仮の目標**は輪郭用の独立学習100～150枚・検証30～50枚・テスト30～50枚。
これだけで十分という意味ではない。実測の誤りの種類と場面分布を見て追加収集する。
別の撮影場所・時間・車種を含める方が、同じ停車を撮り続けた多数のほぼ同一画像より有益。

## 4. 重点画像の抽出を開始する

既存の parking-vision フォルダで研究用Pythonを使用する。下のパスは例。
元動画には文字・検出枠・輪郭が**焼き付いていない**ものを使う。
出力するフォルダは空または新規とし、元動画は変更しない。

例：以前の解析で注目した 154～169秒（旋回）、170～185秒（入庫）付近を追加抽出する。
この秒数は全ての動画に共通ではない。

    cd "$env:USERPROFILE\parking-guide-admin\parking-vision"
    python .\prepare_priority_training_frames.py --video "G:\研究動画\session_A_raw.mp4" --output ".\vehicle_mask_sessions\session_A" --task segment --interval 30 --focus-step 1 --focus 154-169:turning --focus 170-185:bay_entry
    python .\prepare_priority_training_frames.py --video "G:\研究動画\session_B_raw.mp4" --output ".\vehicle_mask_sessions\session_B" --task segment --interval 30
    python .\prepare_priority_training_frames.py --video "G:\研究動画\session_C_raw.mp4" --output ".\vehicle_mask_sessions\session_C" --task segment --interval 30

一つの元動画をA/B/Cに使い回さない。
元動画のSHA256、フレーム時刻、重点タグを annotation_manifest.csv に残す。
その後は既存スクリプトで、**人が**車体輪郭を登録する。

    python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_A"
    python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_B"
    python .\annotate_vehicle_masks.py --images-dir ".\vehicle_mask_sessions\session_C"
    python .\vehicle_mask_dataset.py --train ".\vehicle_mask_sessions\session_A" --val ".\vehicle_mask_sessions\session_B" --test ".\vehicle_mask_sessions\session_C" --output ".\vehicle_mask_dataset\v1"

ラベルが揃うまでは学習しない。準備後は以下を実行する。

    python .\train_vehicle_segmentation.py --data ".\vehicle_mask_dataset\v1\dataset.yaml" --model "yolo11s-seg.pt" --epochs 60 --imgsz 960 --batch 4 --device auto --name "parking_vehicle_masks_v1"

学習後に既存の compare_vehicle_segmentation.py で未使用テストセットのmask mAPを比較し、
evaluate_slots.py と実動画の診断で**誤った空き案内件数、unknown率、ID切り替わり件数**も確認する。

### 障害物の準備は別データセットで

セッション間で学習/検証を分け、画像を先に抽出する。重点タグは例。

    python .\prepare_priority_training_frames.py --video "G:\研究動画\obstacles_A_raw.mp4" --output ".\obstacle_training_sessions\train_A" --task obstacles --focus 20-65:obstacle
    python .\prepare_priority_training_frames.py --video "G:\研究動画\obstacles_B_raw.mp4" --output ".\obstacle_training_sessions\val_B" --task obstacles --focus 20-65:obstacle
    python .\label_obstacles.py --images ".\obstacle_training_sessions\train_A" --validation-images ".\obstacle_training_sessions\val_B" --dataset ".\dataset\obstacles_v1"
    python .\train_obstacles.py --data ".\dataset\obstacles_v1\data.yaml" --base "yolo11n.pt" --epochs 60 --device 0

GPUを持たない環境では device cpu に変更する。
障害物のtrain/val両方に実物の正解枠が必要。元動画が短い時には --focus の時刻を変更する。
既存障害物ラベラーの自動画像分割は検証用画像フォルダを渡さないと
撮影セッション独立を保証しないため、必ず --validation-images を指定する。

## 5. 運用ルールと完了判定

1. 判定済み録画や自動推論枠を正解ラベルとして流用しない。自動生成ラベルを使う場合も人の確認前は教師データとして扱わない。
2. 実車が画面に見えるのに空の正解ラベルで保存しない。「負例」は人が確認した、学習対象のない画像に限る。
3. 公開リポジトリに元動画・フレーム・正解ラベル・撮影場所・ナンバー画像を登録しない。
4. 新しいモデルは別名で保存し、元のVisDrone best.pt、設定ファイル、Supabase、利用者アプリは変更しない。
5. 既存モデルと追加学習モデルを**同じ未使用動画・同じ区画設定**で比較する。
6. 車の見落とし・障害物の見落としで「空き」と出すことを最優先で防ぐ。照合不可はunknownのままとする。
7. 実映像の追加学習完了と現地精度の確認は、ローカルの正解ラベル・GPU・録画が揃ってから行う。

## 6. 根拠

- Ultralytics segmentation dataset: https://docs.ultralytics.com/datasets/segment/
- Ultralytics tracking: https://docs.ultralytics.com/modes/track/
- Ultralytics dataset splits / leakage: https://docs.ultralytics.com/guides/preprocessing-annotated-data/
- 既存の車体輪郭の準備: VEHICLE-MASK-TRAINING.md
- 既存の輪郭比較: SEGMENTATION-PREVIEW.md
- 既存の障害物クラス: label_obstacles.py, data.example.yaml
