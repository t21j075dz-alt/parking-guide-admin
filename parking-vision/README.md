# 駐車場の自動検知・リアルタイム共有（卒業研究）

## できること
カメラ映像から車両と人を検知します。追加学習した障害物モデルを指定すると、カラーコーン・カート・バリケードなども検出対象になります。車ごとに一時的な追跡IDを付け、移動中・駐車中・出庫中・退出済み等を管理します。駐車中と判定された時刻から駐車時間を計測します。映像はSupabaseへ送らず、区画状態と管理者用の匿名車両イベントだけを保存します。

利用者画面は約3秒ごと、管理者画面は約4秒ごとに最新状態を確認します。**WebSocket即時プッシュではなく短周期の自動更新です。**通信不良または20秒以上更新なしの区画は「確認できない」とし、空き案内には使いません。

## Windowsでの準備
管理アプリのリポジトリを取得したら、parking-vision フォルダでPowerShellを開きます。

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config.example.json config.json
notepad config.json
~~~

すでにYOLOとOpenCVを導入した仮想環境なら、再インストールは不要です。利用中の環境で実行してください。

### 設定項目
- facility_id: 管理画面と一致する施設ID。自宅実験用は home-test-001 です。
- camera_id: 任意のカメラ名。複数カメラで同じ名前を使わないでください。
- source: USBカメラなら 0、RTSP/IPカメラなら説明書で確認した映像URL。
- supabase_url、publishable_key: 両アプリの sync-config.js と同じ公開用接続情報。秘密鍵は書かないでください。
- vehicle_model: 車両が検出できる既存の best.pt のパス、または汎用 yolo11n.pt。
- obstacle_model: コーン・カート等を追加学習した best.pt。未学習なら空のまま。
- space_uids: カメラで全体が見える区画IDのみ記入します。例：space_001～space_008。

config.jsonはGitにアップロードされない設定です。**認証パスワード、私有カメラのURL、録画を公開リポジトリへ置かないでください。**

## 1. カメラに写る区画を登録
~~~powershell
python calibrate.py --config config.json
~~~
画面の space_001 などの表示を確認し、その駐車枠の四隅を順番に4回クリックします。実際に見えない枠は s で飛ばしてください。Backspaceはクリック取り消し、rはやり直し、eは入口、xは出口の範囲指定、qで保存して終了です。カメラ角度を変えた場合、最初からやり直してください。

## 2. 通信しない検証
~~~powershell
python -m unittest discover -s tests -p "test_*.py"
python monitor.py --config config.json --preview --dry-run
~~~
空き区画、駐車車両、移動車両を映し、画面内の状態が一致するか確認します。**カラーコーン・カートは障害物学習済みモデルがない限り認識を保証しません。**

## 3. クラウドへ共有
~~~powershell
python monitor.py --config config.json --preview
~~~
Supabaseの管理者メールとパスワードを入力してください。入力したパスワードは画面に表示されず、ファイルには保存しません。管理アプリで施設を選び「カメラによる空き状況・車両追跡」を開くと、枠ごとの最新状態、追跡ID、駐車経過時間が表示されます。

**初期状態では利用者へのライブ公開はOFFです。**管理画面で実際の駐車状況と一致することを確認し、「利用者アプリへ最新の空き状況を公開」をONにしてください。公開するのは区画の状態のみです。自宅実験用施設を公開する際は、場所と利用者のプライバシーに注意してください。

## 4. カラーコーン・カート・障害物を追加学習
正解の枠を付けた画像とラベルを学習用・検証用に分けて用意し、data.example.yaml を参考に data.yaml を作成します。
~~~powershell
python train_obstacles.py --data data.yaml --device cpu
~~~
CUDA対応GPU環境を導入済みなら --device 0 が使えます。学習出力の best.pt を config.json の obstacle_model に指定してください。写真や正解ラベルは同梱していません。モデルのクラス名は traffic_cone、shopping_cart、barrier、bollard、obstacle など monitor.py の BLOCKING_NAMES と対応させてください。

## 判定のルールと限界
| 状態 | 基準 |
|---|---|
| 入場確認中 | 同じカメラに新しく写った車。入口通過の保証はない |
| 移動中 | 駐車条件を満たしていない車 |
| 駐車中 | 同じ区画で5秒以上ほぼ動かない車 |
| 出庫中 | 駐車区画から2秒以上離れた車 |
| 退出済み | 登録した出口の範囲に入った車 |
| 追跡できなくなった | カメラ内で見失った車。退出と推定しない |

車両が区画内に入ると、駐車時間の確定前でもその区画を「使用中」とします。**空き**は車も認識可能な障害物も検出されない状態が5秒以上継続した場合に限ります。見落とし・死角・逆光・夜間で誤判定し得ます。

**1台の車の追跡はカメラ1台の連続映像内のみです。**カメラをまたいで追跡IDを結びつける機能は未実装です。撮影範囲外の駐車時間も計測できません。車両セッションは管理者専用で、利用者へは配信しません。実運用前には保存期間と撮影告知のルールを設けてください。

## 根拠となる公式資料
- https://docs.ultralytics.com/modes/track/
- https://docs.ultralytics.com/datasets/detect/
- https://supabase.com/docs/guides/realtime/postgres-changes
- https://supabase.com/docs/guides/database/postgres/row-level-security

## 卒業研究で確認すること
認識率・駐車枠ごとの正解率・車両IDの入れ替わり回数・駐車時刻の誤差・クラウド更新遅延を日中・夜間・悪天候に分けて評価します。
