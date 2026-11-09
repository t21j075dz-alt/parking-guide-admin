# 駐車場構造の追加学習：第3のYOLOセグメンテーション

## 追加対象

| ID | YOLOクラス | 対象 |
|---|---|---|
| 0 | parking_space | 見える駐車枠の床面 |
| 1 | parking_line | 白線・区画線 |
| 2 | drive_aisle | 通路の路面 |
| 3 | pedestrian_crossing | 横断歩道の塗装 |
| 4 | direction_arrow | 路面の進行方向矢印 |

車両・障害物とは別の路面レイアウト専用セグメンテーションモデルとして試験学習します。
車両893個・障害物346個のラベルと旧モデルは変更しません。
見えない区画境界を推測して教師ラベルに含めないこと。

## 統合画面の第3モードを開く

PowerShellで以下を実行します。

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
$researchPython = "$env:USERPROFILE\parking-yolo-home\.venv-gpu\Scripts\python.exe"
& $researchPython .\unified_annotator.py --start-mode layout
~~~

以前の241枚の original 写真フォルダを選択すると、
同じ annotation_workspaces/photos_242 の保存領域で登録できます。
画面上部「区画・白線・路面（輪郭をクリック）」のモードです。

左クリックで輪郭の各点を指定、Enterでその形を確定、
「確認して保存」でレイアウトだけ保存します。対象が本当にない写真のみ
「対象なしとして保存」を押してください。
未確認の写真は学習に含めず保留にします。
表示倍率・Ctrl+Z・前の画像などは従来どおり利用できます。

## 既存のラベル数と不足クラスの確認

~~~powershell
& $researchPython .\training_gap_report.py --workspace ".\annotation_workspaces\photos_242"
~~~

車両・障害物・路面の各クラス数、登録済み枚数、未登録枚数を表示します。
データは読み取り専用です。

## 路面の目視確認済み画像だけを試験学習する

241枚すべてをやり直す必要はありません。
ただし各画像で対象が一部しか囲まれていない場合は、
未ラベルを背景と誤学習するため、その写真を保留にしてください。
正例を含む写真が必要です。

~~~powershell
& $researchPython .\unified_annotator.py export --mode layout --train-workspace ".\annotation_workspaces\photos_242" --output ".\reviewed_photo_datasets\layout_pilot_v1" --train-only --only-reviewed
~~~

ここで --only-reviewed はlayoutの試験学習専用です。
車両と障害物の既存データは全画像のラベルが必須のままです。
元写真・教師ラベルの上書きはしません。

## GPUで別モデルを試験学習する

~~~powershell
& $researchPython .\train_reviewed_photos.py --task layout --data ".\reviewed_photo_datasets\layout_pilot_v1\dataset.yaml" --model "yolo11n-seg.pt" --epochs 20 --imgsz 640 --batch 2 --device auto --name "layout_pilot_v1" --accept-train-only
~~~

出力先は runs/unified_training/layout_pilot_v1/weights/last.pt の予定です。
GPUメモリ不足の場合はバッチを1へ下げて、新しい実験名で実行します。
独立した検証画像なしの試験です。本番アプリやSupabaseには自動反映しません。

## さらに今後学習できるもの（まだ未実装）

- 前後輪の接地点：YOLO Pose向けのキーポイント教師データが必要。
- 歩行者・自転車・二輪車：既存モデルにも対応クラスがあるため、まず誤検出例を分析。
- 入庫・出庫：動画の連続フレーム・トラッカー・区画状態を併用。
- 夜間・雨・逆光：新しい物体クラスではなく撮影条件や拡張データとして扱う。
- 区画ID・自動マップ連携：画面の位置とマップ座標を校正して結び付ける別処理が必要。

## 公式資料

- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/datasets/pose/
- https://docs.ultralytics.com/modes/train/
- https://docs.ultralytics.com/modes/val/
