# 研究室PCの初期セットアップ（Windows）

2026年10月30日時点の卒業研究用。GitHubの同一コードを研究室PCに用意し、既存Supabaseプロジェクトをそのまま利用します。研究室PCの実機と管理権限は未確認です。

## 事前準備

Windowsでソフトの導入が許可されていることを確認してください。Git for Windows、Python 3.11または3.12（Python Launcherのpyコマンド含む）を用意してください。研究用の非公開リポジトリへアクセスするため、自分のGitHubアカウントでログインできる必要があります。

- Git公式: https://git-scm.com/install/windows
- Python公式: https://www.python.org/downloads/windows/
- venv公式: https://docs.python.org/ja/3.11/library/venv.html
- YOLO公式: https://docs.ultralytics.com/quickstart

## 1. セットアップ

PowerShellで次を実行してください。

~~~powershell
cd $env:USERPROFILE
git clone https://github.com/t21j075dz-alt/parking-guide-admin.git
cd .\parking-guide-admin
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_lab_pc.ps1
~~~

すでに管理アプリのフォルダがある場合は、cloneを省き、既存フォルダに移動しgit pull --ff-onlyで更新してから実行します。ローカルの変更は上書きせず、問題があれば処理を停止します。

自動で取得するのは次の3件です。

- 研究用管理アプリ：ユーザーフォルダの parking-guide-admin
- 利用者アプリ：ユーザーフォルダの parking-guide-user
- YOLO本体：ユーザーフォルダの parking-vision （GitHub上のリポジトリ名はparking-vision-research）

さらに、parking-vision内の .venv-cpu にPython環境を作成し、管理者アプリのparking-vision/requirements.txtを使用してライブラリを導入・基本動作確認します。クラウドへの送信・カメラ共有は開始しません。

## 2. 学習済みモデルを移す

自宅デスクトップから**実際に使用している学習済みbest.pt**を、USB等で研究室PCへ移してください。これまでの環境の候補は以下です。

- ユーザーフォルダの parking-yolo-home/runs/parking_objects/visdrone_finetune_v1/weights/best.pt
- ユーザーフォルダの parking-vision/weights/visdrone_finetune_best.pt

研究室PCのEドライブにモデルを一時保存した例です。

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_lab_pc.ps1 -ModelPath "E:\研究用\best.pt"
~~~

コピー先は、研究室PCのユーザーフォルダの parking-vision/weights/visdrone_finetune_best.pt です。既存のモデルと異なるファイルがあった場合、上書きせず停止します。ファイル内容のSHA-256でコピーを照合します。

**Pythonの仮想環境フォルダをPC間でコピーしないでください。** 各PCで作成します。学習モデルと動画はGitHubに含まれていません。

## 3. 動画・設定ファイルを別途移す

自宅の parking-guide-admin/parking-vision フォルダから、必要なファイルだけ研究室PCの同じ場所にコピーします。

| ファイル | 役割 |
| --- | --- |
| config_video_demo.json | 録画のループ判定をする設定 |
| config_from_laptop.json | 録画設定を最初に生成する場合の元設定 |
| config.json | 自宅USBカメラ用設定。別PCでは再確認が必要 |
| config_camo.json | Camo用設定。接続先・区画の再確認が必要 |
| 元の映像_001.mp4等 | 録画実験の入力動画 |
| 研究CSV・出力フォルダ | 過去の比較実験を続ける場合だけ |

YOLO判定枠をすでに描いた出力動画を、元動画の代わりに入力しないでください。持ち運びは学内の個人情報・撮影データの取扱規則に従ってください。

**移行後に各JSONの vehicle_model のパスを研究室PCの実際のモデル保存先へ直すことが必要です。** configファイルはバックアップしてから編集してください。Supabaseの公開用接続先は既存のプロジェクトと一致するか確認します。service_roleや秘密鍵、パスワードをGitHubへ追加しないでください。

参考：存在する設定ファイルだけバックアップし、vehicle_modelを新PCのモデルに置き換える方法です。

~~~powershell
$folder = Join-Path $env:USERPROFILE "parking-guide-admin\parking-vision"
$model = Join-Path $env:USERPROFILE "parking-vision\weights\visdrone_finetune_best.pt"
if (-not (Test-Path -LiteralPath $model)) { throw "モデルファイルがありません" }
foreach ($name in @("config.json", "config_video_demo.json", "config_camo.json")) {
    $file = Join-Path $folder $name
    if (-not (Test-Path -LiteralPath $file)) { continue }
    Copy-Item -LiteralPath $file -Destination ($file + ".before-lab-path.bak")
    $settings = Get-Content -LiteralPath $file -Raw -Encoding UTF8 | ConvertFrom-Json
    $settings.vehicle_model = $model
    [System.IO.File]::WriteAllText($file, ($settings | ConvertTo-Json -Depth 30), [System.Text.UTF8Encoding]::new($false))
    Write-Host "更新: $name"
}
~~~

## 4. 動作テスト

学習モデル、録画用設定、元動画が移ったら、まずクラウドに送らないモードで確認します。

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin\parking-vision"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_video_demo.ps1 -Video "E:\研究動画\映像_001.mp4"
~~~

動画が末尾に達すると先頭から繰り返されます。QキーまたはCtrl+Cで停止します。最初に映像上の区画枠が正しく重なっているか確認してください。

共有テストは、録画動画でYOLO案内を実演.cmdを開き、録画実演専用への共有を選んで明示的に承認します。録画の状態を実カメラ施設へ送ることはできない設計です。研究室での初回確認では共有を選ばないでください。

## 5. 実カメラ・Camoの注意点

- USBカメラ番号・Camoの接続状態はPCごとに違うので、映像を目視して再選択します。
- 映像の画角や設置位置が変わったときは駐車区画の再校正が必要です。自宅カメラ用の校正座標は研究室カメラへそのまま転用しません。
- 別の場所で撮影した映像を自宅駐車場の現在の空き情報として送信しないでください。
- 同じ施設IDへ複数PCから同時にライブ送信しないでください。
- 研究室PCにNVIDIA GPUがない場合でもCPU判定は可能ですが、FPSや処理時間は変わります。

## 6. 普段の更新

コードを更新した後は、各PCで次を実行します。

~~~powershell
git -C "$env:USERPROFILE\parking-guide-admin" pull --ff-only
git -C "$env:USERPROFILE\parking-guide-user" pull --ff-only
git -C "$env:USERPROFILE\parking-vision" pull --ff-only
~~~

GitHubはコードを同期し、Supabaseはレイアウト・状態・音声関連を共有します。学習済みモデル、動画、校正JSON、各PCの録画は各端末に残ります。ブラウザのローカル保存やPWAキャッシュも端末ごとなので、クラウドで保存できたデータと端末だけのデータを区別してください。

ソースが一致していてもカメラやCPU/GPUが違えば判定結果・速度が完全一致するとは限りません。卒業研究の比較実験では、使用モデル、解像度、信頼度、トラッカー、Pythonライブラリのバージョンを記録してください。
