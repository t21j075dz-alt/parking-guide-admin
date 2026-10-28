# Windows：USBカメラの写真配信

YOLOの学習済みモデルや駐車枠の登録前でも、USBカメラから写真だけを配信できます。空き状況や車両追跡の値は更新しません。

## 起動

1. このリポジトリを最新の状態にします。既存のチェックアウトでは `git pull --ff-only` を実行してください。ローカル変更があるため更新できない場合は、変更を破棄せず表示内容を確認します。
2. Windowsのカメラアプリなど、カメラを使用しているアプリを終了します。
3. `parking-guide-admin/parking-vision` フォルダーでPowerShellを開きます。
4. 次を実行します。メールアドレスは実際の管理者のものを指定してください。

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\start_camera_photos.ps1 -Camera 1 -Email "管理アプリのメールアドレス"
```

USBカメラの実映像を見て、正しいカメラなら **Y**。違う場合は **Q** で中止し、`-Camera 0` や `-Camera 2` で試します。番号だけで内蔵・外付けは判別できません。確認前に写真やログイン情報を送信しません。

その後、管理アプリのパスワードを入力します。入力中は文字が表示されません。パスワードをファイルへ保存することはありません。Supabaseの管理用アクセストークンはPCに不要です。

配信先の初期値は `home-test-001`（自宅テスト施設）です。別施設に配信する場合は、その施設の固定IDを `-Facility` に指定します。録画ファイルは入力できません。

## Pythonが見つからない場合

既存の研究用Pythonを `-Python "C:\...\python.exe"` で指定できます。必要なのはPython 3.10以降とOpenCVです。YOLOは不要です。

新しい環境を作る場合は、Python 3.12がインストールされているPCで、`parking-vision` 内から次を実行します。

```powershell
py -3.12 -m venv .venv-photos
.\.venv-photos\Scripts\python.exe -m pip install "opencv-python>=4.8,<5"
```

Pythonがインストールされているか不明な場合は `py --list` で確認してください。起動ツールは `.venv-photos` を自動検出します。

## 管理画面と公開

管理アプリにログインし、**自宅テスト用施設**を選び、**カメラを確認**を開きます。写真を約5秒ごとに更新し、取得解像度と撮影時刻を確認します。実際の撮影解像度はカメラの既定設定によります。最高解像度の自動選択は行いません。JPEGが2MBを超えた場合はエラーになり、`publish_camera.py --width ... --height ...` で解像度を指定する必要があります。

初期状態では管理者向けだけを配信します。利用者向けにも5分ごとに公開するには、起動コマンドへ **`-PublicPhotos`** を付けてください。人物・ナンバーの自動加工は行いません。

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\start_camera_photos.ps1 -Camera 1 -PublicPhotos
```

終了はカメラ画面で **Q**、またはPowerShellで **Ctrl+C**。更新が停止すると管理写真は30秒、公開写真は6分で非表示になります。PCの電源やネットワークを切ると配信は止まります。ブラウザーの公開ON/OFFやYOLOの空き状況配信とは別の機能です。

動作確認：Pythonの既存テスト59件（写真起動4件を含む）で確認。Windows実機のUSB接続・音声出力・カメラ解像度は利用者PCでの確認が必要です。
