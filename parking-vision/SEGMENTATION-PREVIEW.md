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


## 2026-11-05：転回時のID欠落を根本改善する新モード

**重要：旧モードの `-SegmentationPreview` と新モードは別です。**
旧モードは「従来YOLO検出・追跡＋別モデルによる輪郭描画」だったため、
輪郭が出ていても従来YOLOの追跡IDが空欄になる問題が残っていました。

新しい `-SegmentationTracking` では **YOLO11-segを検出器・
インスタンスマスク生成器・追跡器として一体利用** します。
2モデルの検出枠をIoUで後付け対応付けする必要がなくなります。
また、**追跡対象のID更新と、駐車区画への関与判定を分離** しました。
車両が区画の少し外側を旋回していても、全画面で匿名IDを追跡します。
駐車状態の確定は、従来どおり監視対象・時間・区画の条件が必要です。

### 実行（最初は録画で比較）

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking
```

モデルの能力を比較する場合は（処理は重くなります）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking -SegmentationModel "yolo11s-seg.pt" -SegmentationImageSize 960
```

モデルファイルが未保存なら初回はUltralyticsのダウンロードが必要です。
こちらは **`-Share` と併用不可** で、クラウドには送信しません。
録画の元動画と既存のカメラ設定は上書きしません。

### 実験で確認する区間と判定

- 最初に `車両輪郭_比較診断.csv` で `stable_track_id` の欠落数を比較
- **154.3〜157.7秒、164.7〜168.6秒**：従来モデルでは各35件・40件の生ID欠落
- 旋回中にID1が継続しているか、新たなID2などへの誤分裂がないか
- 他車両・人物・植え込みを誤って同一車両に結合していないか
- 実画像の車体輪郭が向きにかかわらず車体に沿っているか
- 区画の占有・空きに誤判定が生じていないか

このモデルだけで「全方位100%」は保証できません。
改善が足りなければ、カメラの **前／後／横／斜め／旋回中**
の *元動画* からバランス良く学習画像を用意し、
車体ごとの輪郭をアノテーションしてカスタムsegモデルに再学習します。
YOLO判定線が焼き付いた **判定後の動画** は学習用の元画像に
しないでください。正解データがない状態で精度改善を数値保証しません。

参考：
- https://docs.ultralytics.com/modes/track/
- https://docs.ultralytics.com/tasks/segment/
- https://docs.ultralytics.com/datasets/segment/


## 2026-11-05：転回時の追跡枠と駐車位置判定を改良

今回の実験CSV（`車両輪郭_比較診断(2).csv`）では3,283件中、
**矩形下端の区画候補と輪郭下端の区画候補の不一致が24件**でした。
171.8〜173.6秒付近では、旧方式が区画を決められない一方、
マスクのサンプルは`space_003`を候補としています。

### 実装した改善（`-SegmentationTracking` のみ）

1. **車両の表示枠**：同一匿名IDの表示枠を時間方向に平滑化し、
   旋回による1フレーム単位のがたつきを軽減します。
   元の検出矩形は一切変更しません。
2. **車両の向き**：車体マスクの最小外接回転矩形の長軸を表示。
   極端に正方形に近い輪郭では方向を表示せず、180度をまたぐ角度は
   2倍角の平均で連続性を保ちます。
   **長軸は車の前後方向を識別しません。**
3. **停車と移動の区別**：車両のマスク面積重心を移動の補助指標に
   使います。転回で検出枠の下端だけが動いた場合に、車の移動と
   誤認する可能性を減らします。ただし地面上の移動量ではありません。
4. **区画候補の融合**：従来の矩形下端と車体輪郭下端の候補が
   同じなら採用。どちらか一方だけが候補になる場合は同一匿名IDで
   1.25秒以上かつ5回以上連続して初めて暫定採用。
   **両者が違う区画を示したらどちらも確定せず「確認中」**にします。
   最終的な駐車確定には従来の5秒間の観測も必要です。
5. **ログ**：`車両輪郭_比較診断.csv` に
   `fused_zone`、`fused_zone_basis`、`visible_axis_degrees`を記録。
   `駐車区画_判定診断.csv`には矛盾や未確定の理由を記載。

**重要**：これは平面画像から得られる「区画候補」を安全に融合する
改修であり、車両のタイヤの接地点や真の地面上の投影を推定したもの
ではありません。車の屋根・側面に生じる視差を完全には補正しません。

### 同じ録画を再比較する

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking
```

`-SegmentationTracking` は以前と同じく **研究用のクラウド非共有モード**
です。従来の動作に戻すにはスイッチを外してください。

### 高所カメラを設置する際の必須作業

- 駐車場の全区画と進入/退出の動線が映るよう、画角を実写で確認
- 屋根・壁・柱や植栽によって車が一時的に隠れない位置を選択
- 駐車場の区画線の**地面側の四隅**を、変更後の映像で再登録
- 同じ車を、前面・背面・左右・斜め・旋回途中で撮影し検出・追跡を確認
- 地面上の正確な座標が必要な場合は、路面上の既知位置（4点以上）
  を使ったカメラ校正と、車体の接地点を特定する追加モデルまたは
  対象車種の3次元寸法等による補正が必要。**屋根のマスクをそのまま
  路面へ変換しても正確な車体底面にはなりません。**

この段階で実カメラ施設の占有判定やSupabaseへの公開を自動で
切り替えることはしません。録画で旧/新方式の区画誤帰属、
偽の出庫、占有の確定遅延を比較してから判断してください。

根拠：
- https://docs.ultralytics.com/tasks/segment/
- https://docs.ultralytics.com/modes/track/
- https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html
