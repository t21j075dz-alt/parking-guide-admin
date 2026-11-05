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

## 2026-11-05: 角度差・区画誤帰属・追跡枠の揺れを低減（追加機能）

`-SegmentationTracking` に、**動画実験限定の保守的な区画候補融合** を追加しました。

1. 既存の矩形下端方式と、YOLO-segの車体下側輪郭が**同じ区画**を指す → 一致として採用
2. 2方式が**別の区画**を指す → 区画を特定せず「確認中」に留める（誤占有防止）
3. 矩形では決められず、輪郭だけが一区画を指す → 輪郭信頼度>=0.80、矩形一致>=0.80、下側輪郭点>=7、同じ匿名追跡IDで**2秒以上・5フレーム以上**一貫した場合のみ区画候補として認める
4. 輪郭がない、他区画を指す、IDがない → 従来方式、または不明扱い
5. **検出枠の揺れを緩和**：追跡IDごとに表示専用の矩形を平滑化。実際の駐車判定に使うYOLO検出矩形、フレームごとの生映像は変更しない

これは「車体の見える輪郭」の融合であり、地面に接する正確な車体投影を求めたものではありません。高所カメラの本当の地面座標を求めるには、区画四隅に加え、カメラの設置高さ・角度等を含むキャリブレーションが必要です。隣の区画に車体上面が重なる影響を完全には解消しません。

### 同じ動画で比較する方法

```powershell
cd "$env:USERPROFILE\parking-guide-admin"
git pull --ff-only
cd .\parking-vision
# 新方式（セグ追跡＋時間安定性を使う区画融合）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking
# 対照実験（同じセグ追跡＋従来の矩形下端のみ）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking -LegacyZoneGeometry
```

`車両輪郭_比較診断.csv` に `demo_geometry_basis` と `demo_geometry_zone` を追加しました。`agreement`、`conflict`、`mask-pending`、`mask-temporal` の違いを確認できます。`-Share` との併用は禁止され、Supabaseへの書き込みは発生しません。

今回の改善の有効性は、同じ元動画を各方式で再推論し、特に170〜185秒の入庫区間、車体の大きい角度変化、駐車中の誤区画遷移を目視正解と突き合わせて評価してください。

## 2026-11-05 追加修正：短い信頼度低下と隣接区画の表示ちらつき

ユーザー提供の `車両輪郭_比較診断(3).csv` と
`区画状態の変化(20261105-070741).csv` では、170秒台の3番区画への入庫で
輪郭による区画候補が続く一方、信頼度が一時的に0.80未満になり、
`mask-temporal` は発生しませんでした。また4番区画は
172.7秒「確認中」→173.3秒「空き」→173.4秒「確認中」→173.7秒「空き」
の短い切り替わりがありました。

**変更点（`-SegmentationTracking` かつ比較実験のみ）**

- 同じ車両ID・同じ区画に対する有効な輪郭の証拠を **1.6秒以上・5観測以上** 継続確認（従来2秒）。低信頼度1フレームでは履歴を削除せず、強い証拠としては加算しません。
- 高信頼度の閾値は0.80→0.78に調整（区画候補単独の強いフレームにのみ使用）。輪郭と矩形のIoU0.80以上、下部輪郭点7点以上、別区画の矛盾なし、同じ追跡ID、途切れ0.75秒以内という安全条件は維持。
- 従来の矩形方式が**同じ**区画を検出し始めても、過去の輪郭証拠を消しません。異なる区画を示したら履歴をリセットし「確認中」扱い。
- 4番区画のように一度「確認中」になった区画は、その根拠が消えてから **1.0秒** は「空き」に復帰させません。不確実な車両が現れた際の「空き→確認中」は即時です（安全側）。
- 駐車確定に必要な累積5秒の観測、停車・出庫証拠、通常モードの判定、Supabaseへの共有禁止は変更しません。

`車両輪郭_比較診断.csv` の `demo_geometry_basis` では、
`mask-weak-hold` が一時的な信頼度低下の保留を表し、
`mask-temporal` が時間条件を満たした輪郭由来の区画候補です。

**比較方法**：下の2コマンドを同じ元動画で実行し、`170〜185秒`、
とくに3番区画の確定時刻と4番区画の状態変化回数を比較します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "G:\研究動画\20261029_165836_579397\映像_001.mp4" -SegmentationTracking -LegacyZoneGeometry
```

なお、輪郭から取得した下側座標は地面の接地点の計測値ではないため、
画像上の車体が隣接枠を大きく覆う条件では、区画を「確認中」にすることがあります。
