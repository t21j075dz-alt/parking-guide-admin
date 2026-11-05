# YOLO11 車両セグメンテーション比較実験（安全なプレビュー）

## この機能でできること

既存の YOLO 車両検出／BoT-SORT／安定 ID は変更しません。追加の
`yolo11n-seg.pt` で車ごとの **画像上で見えている車体の輪郭** を抽出し、
元の YOLO 検出枠へ 1 対 1 に対応付けます。

- 黄色の線：車体のセグメンテーション輪郭
- 半透明オレンジ：見えている車体マスク
- 紫の点：マスクの下側シルエットを9列でサンプリングした位置
- 比較 CSV：従来の矩形下端による区画候補と、輪郭下端の参考候補
- 判定動画：従来の YOLO 判定映像に輪郭を合成して研究フォルダへ保存

**重要：マスクの下辺はタイヤの接地位置や車体の真下ではありません。**
屋根、バンパー、側面、遮蔽、カメラの角度が影響します。
この段階では、マスクの区画候補は **比較用だけ** に使い、
駐車状態・追跡 ID・Supabase の保存結果に影響させません。

## 実行方法（Windows／既存の研究環境）

既存の録画実演の準備が済んでいる PC で、管理者レポジトリを更新します。

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationPreview
```

- `-Share` **なし**：録画・診断だけ。Supabase へ送信しません。
- Q キーで終了。録画のループ再生は従来どおりです。
- 最初の実行時に学習済み `yolo11n-seg.pt` が未配置なら、Ultralytics が
  ダウンロードします。ネット接続が必要です。
- 既存の `best.pt` などの車両検出モデルは変更・上書きしません。
- 解析は車両検出とマスク推論の2モデルになるため、処理が遅くなり得ます。

速度・輪郭の細かさを比較したい場合：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationPreview -SegmentationImageSize 960
```

自前で学習したセグメンテーションモデルがある場合：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationPreview -SegmentationModel "C:\path\to\best-seg.pt"
```

セグメンテーションなしに戻す場合は、`-SegmentationPreview` を外します。
既存スクリプトや `config.json` の変更は不要です。

## 保存される診断項目

各実行の研究フォルダ内に `車両輪郭_比較診断.csv` を追加します。

| 列 | 内容 |
| --- | --- |
| video_seconds | 録画内の時刻、またはライブ解析時刻 |
| stable_track_id / raw_track_id | 既存の匿名追跡番号 |
| legacy_zone | 既存の底面矩形方式の区画候補 |
| segmentation_zone | マスク下端を使った比較用区画候補 |
| segmentation_match_iou | 既存矩形とセグメンテーション検出矩形のIoU |
| segmentation_confidence | 輪郭検出モデルの信頼度 |
| lower_points | 輪郭下端を抽出できた点数 |
| match_state | 輪郭と既存追跡が対応付いたか |

輪郭の実画素や車両画像は追加のクラウド表に送信しません。
ただし、従来どおり研究用 PC の判定動画にはカメラ画像が記録されます。

## 判定結果を比較する際の注意

- マスクが取れない場合は空欄にし、矩形下端の従来判定だけを維持します。
- 違う車へのマスク割り当てを防ぐため、四輪／二輪の種類が一致し、
  検出枠のIoUが0.30以上の候補を1対1で対応付けます。
- マスクの下辺が複数区画にまたがる場合は、比較候補を空欄にします。
- 3番・4番区画、旋回時、接近する2台、画面端、暗所などを比較してください。
- 精度が改善したかどうかは、映像を人が確認して正解ラベルを付け、
  旧方式との誤帰属件数を比較して初めて判断できます。

## 単体テスト

```powershell
python -m unittest discover -s tests -p "test_vehicle_segmentation.py"
```

これは数値処理、同一マスクの重複割当防止、従来判定の不変性、
画像を上書きしない描画、比較CSVの項目を確認します。
実映像のモデル精度そのものはPC上で別途検証してください。

参考：Ultralytics 公式の [Segment task](https://docs.ultralytics.com/tasks/segment/) と
[YOLO11](https://docs.ultralytics.com/models/yolo11/)。


## 2026-11-05: 転回時の枠ずれ・生ID欠落対策

録画実験「YOLO判定_001(9).mp4」と「車両輪郭_比較診断.csv」の転回を診断し、既存の `-SegmentationPreview` に次を追加しました。

- **表示用追跡枠の補正**：車体マスクに沿ったタイトな矩形を計算。マスク信頼度0.65以上、矩形同士の一致度0.70以上、面積比0.50～1.20、元のYOLO検出枠とのIoU0.45以上を満たす時だけ表示枠に利用。実際の駐車判定に使用する `bbox` は変更しません。
- **生IDが欠落した車の補完**：直前0.75秒以内に見えていた同じ四輪車で、両フレームに良好な輪郭があり、マスク矩形のIoU0.50以上、かつIoU0.70未満の場合は色の一致も必要、一意に対応する時だけ安定IDを引き継ぎます。複数候補や別の可視生IDがある場合は無理につなぎません。
- **比較CSVの追加列**：`id_mask_bridged`（マスクを根拠としたID補完）、`display_bbox_source`（表示枠が従来/輪郭のどちらか）。従来の区画候補列は継続出力。

注意：この方法でも、マスク自体が間違った車に付く場合や2台の車両が重なる場合、追跡できないことがあります。確実性を優先して不明とします。**学習済みYOLOモデルの重み、元の動画、駐車区画の設定は変更しません。**

既存の実行コマンドをそのまま再実行して確認します。

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationPreview
```

重点確認：録画154～158秒と164～169秒の `id_mask_bridged`、153～164秒の輪郭／検出枠の見た目、159～162秒の生ID16の誤検出。
