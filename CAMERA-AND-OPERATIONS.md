# 営業時間・共用区画・USBカメラ写真

## 営業時間と共用区画

左側の「営業時間・休業・共用区画」から設定します。表示用の営業時間と曜日別の時間判定は別項目です。「曜日ごとの営業時間で『休』を自動表示」をONにすると、日本時間で営業状態を判定します。夜間営業・24時間営業に対応します。未登録の営業時間は推測しません。「休業中」は営業時間より優先します。保存は既存の端末保存・履歴・クラウド同期を使います。

大型枠と、その内部に重なる普通車枠に同じ共用グループ名を設定してください。いずれかが使用中・障害物あり・未確認なら、グループ全体を案内対象から外します。全区画の空きが確認できた場合だけ、希望車種の区画を案内します。区画の形状から重複を自動推定しないため、グループ設定が必要です。カメラには各構成区画の判定範囲を登録してください。

## カメラ写真の導入

1. Supabase SQL Editorで `camera-snapshots.sql` を適用します。本変更では本番DBへ適用していません。
2. `parking_camera_operators` に、利用する管理者の `auth.users.id` を登録します。単なるログイン済み利用者にはカメラ権限を与えません。
3. カメラを接続したPCの `parking-vision/config.json` に `camera_snapshots_enabled: true` を設定します。利用者向けにも配信する場合だけ `public_snapshots_enabled: true` にします。初期値はいずれもOFFです。
4. 通常どおり `python monitor.py --config config.json` で起動し、管理アプリでログインして「カメラを確認」を開きます。`--dry-run` は写真も送信しません。

管理者向けは5秒ごとのJPEG静止画です。「写真を大きく表示」で取得した解像度のまま確認できます。動画ストリーミングではありません。利用者向けは5分ごと、幅1280px以内の別画像です。複数カメラを選べます。管理画像は30秒、公開画像は6分を超えると表示しません。撮影時刻を表示し、切断後の写真を現在の状況として残しません。

USBカメラの `camera_capture_width` / `camera_capture_height` で希望解像度を指定できます。0/0はカメラの既定値で、最高画質を保証する設定ではありません。対応解像度は実機で確認してください。画角が変わった場合は区画を再登録します。管理向けJPEGは品質95、1枚2MBまでで、超過時は送信エラーになります。非同期動画配信や最大解像度の自動列挙には未対応です。

任意の `public_snapshot_masks` に `[x1,y1,x2,y2]`（0〜1の正規化座標）を指定すると公開写真だけを黒塗りできます。自動の人物・ナンバー認識は行いません。公開を即停止する場合は `parking_camera_public` の該当行を削除または `is_published=false` とし、送信元でも公開設定をOFFにします。最新行のみ上書きし、写真の履歴は蓄積しません。

## 検証

```sh
node --test tests/*.test.cjs
NODE_PATH=/workspace/parking-cloud-tools/node_modules CHROMIUM_PATH=/usr/bin/chromium node tests/experience-browser.cjs
cd parking-vision
python -m unittest discover -s tests -p 'test_*.py'
```

ブラウザーテストは外部通信をモックし、本番の書込みや実カメラ接続は行いません。`browser-smoke.cjs` と `interaction-browser.cjs` も従来どおり使用できます。
