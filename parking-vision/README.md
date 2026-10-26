# 録画動画・写真を使う次の研究実験（2026-10-27）

**初めはPC内だけで解析し、クラウドへは公開しません。**

## 1. 録画動画を分析する

Windowsなら **「動画テストを開始.cmd」をダブルクリック**します。初回はconfig.jsonが作られるので、開いたメモ帳で施設ID・カメラ・公開用キー・駐車枠IDを設定して保存します。

**初回に登録区画がない場合は、動画の写真に写る駐車枠を登録する画面が自動で開きます。**マウスで4点クリックして登録してください（カメラを動かしたときも再登録）。

PowerShellからの例：

    .\start.ps1 -Mode calibrate -Video "C:\Users\Owner\Desktop\parking-yolo-starter\test_house1.mp4"

登録後、録画を判定する：

    .\start.ps1 -Mode video -Video "C:\Users\Owner\Desktop\parking-yolo-starter\test_house1.mp4" -Preview

以前使っていたYOLO環境を指定するには、末尾に次を追加します（実際のパスに変更）。

    -Python "C:\Users\Owner\Downloads\parking-yolo-starter\.venv\Scripts\python.exe"

録画動画はSupabaseへ送信しません。reportsフォルダに次の結果を保存します。

| ファイル | 内容 |
|---|---|
| 駐車枠の状態.csv | 動画内の経過時刻、区画ごとの判定、検出件数 |
| 車両の行動記録.csv | 一時的な追跡IDと駐車中・出庫中・退出済み等の変化 |
| 分析結果.json | フレーム数、状態の出現割合、確定した駐車時間など |
| 判定結果_確認用.mp4 | -SaveVideo 指定時のみ。個人や車の情報が写るので公開しない |

**「空きだったフレームの割合」は正解率ではありません。**精度を示すには映像を目視した正解データとの比較が必要です。

## 2. コーン・カートの写真に正解の四角を描く

PowerShellから次を実行します。

    .\start.ps1 -Mode label -Images "C:\Users\Owner\Desktop\parking-yolo-starter\myparkingphoto_20261022\original"

表示される画面で、①種類を選択→②障害物をドラッグで囲む→③「確認して次の写真」をクリックします。
障害物が**ないと目視で確認した画像**は枠を描かずに保存します（負例）。
物体が見えない・判断できない写真は「この写真を飛ばす」を押します。
車だけが写った写真では、カラーコーン・カートの検出器は学習できません。実際の対象物の写真が必要です。

別の日・別の場所の検証写真があれば次のように指定します。

    .\start.ps1 -Mode label -Images "C:\parking\train" -ValidationImages "C:\parking\val"

検証用を指定しないと約20%を自動分割しますが、連写など似た写真では見かけの精度が高くなることがあるため、卒業研究では別日・別場所を推奨します。

正解画像を登録した後の学習：

    .\start.ps1 -Mode train

学習用と検証用の両方に対象物がなければ実行を中止します。学習終了後、生成された best.pt を config.json の obstacle_model に指定します。

## 3. 実カメラでテスト→共有

クラウドに送らず判定だけ確認：

    .\start.ps1 -Mode camera

目視で区画判定が合っていることを確認し、管理者権限と撮影告知を確認してから共有を開始：

    .\start.ps1 -Mode cloud

「共有」と入力する確認の後、Supabase管理者のログインが必要です。
**録画ファイルを現在の空き状況として誤公開しないよう安全装置を設けています。**

Windowsの通常のPowerShellでps1実行が禁止されているときは、自分で取得したファイルに間違いがないことを確認してから、付属の「動画テストを開始.cmd」を開いてください。

---
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
