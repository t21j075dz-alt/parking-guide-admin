# カメラ映像と管理マップの4点位置合わせ（第1段階）

管理者アプリのマップを**区画の唯一の元データ**とし、固定カメラの視点に合わせて各駐車区画の四隅を一括生成します。カメラ側で全区画を手動描画する必要をなくすための導入実験です。

## 対応範囲
- マップで保存した区画の位置・幅・高さ・回転角度を利用。
- マップと映像で対応する床面上の**4組の点**から射影変換を推定。
- 全区画の画像上の四角形を生成して重ね表示。YOLOが使う0～1座標でJSON出力。
- 区画IDは変えない。未撮影の区画がある場合は保存せず再設定を促す。
- import_map_alignment.py は初期状態では確認表示だけ。明示承認時のみバックアップして space_zones を更新。
- 画像はブラウザー内で処理し、JSONに画像データは含まれない。

**未対応**：カメラを置くだけで白線から自動的に対応点を決める処理、カメラ移設の自動検知、非平面の駐車場の校正、YOLOの本番自動切替。本機能の検証中は実カメラの判定を無断で上書きしません。

## 管理アプリの操作

1. 対象の施設（自宅実験では「実験用駐車場（自宅駐車場リアルタイム用）」）を選ぶ。
2. マップの駐車区画を確認する。区画ID（space_001 等）がYOLO側の space_uids と一致している必要がある。
3. 左の「カメラとマップの位置合わせ」を開き、「位置合わせを開始」。
4. カメラIDに parking-vision/config.json の camera_id と同じ値を入力。
5. 「現在のカメラ写真を使用」、または保存済みの画像（JPEG/PNG/WebP）を選ぶ。
6. 左のマップ→右の映像の順に、同じ床面上の場所を4組クリック。できるだけ広く分散した白線の角や路面標示を使う。**車体の屋根など床面以外の点は選ばない。**
7. 「全区画の位置を自動計算」。右の映像で緑の四角形が実際の駐車枠と一致するか全区画を目視確認。
8. 問題なければ「確認済み設定JSONを保存」。管理マップを変更した場合は再計算と確認を行う。

## 既存YOLOへ取り込む（Windows PowerShell）

JSONを出力しただけではYOLOの設定は変更されません。取り込みスクリプトは parking-guide-admin/parking-vision にあります。

まず確認のみ：

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin\parking-vision"
python .\import_map_alignment.py --config .\config.json --alignment "$env:USERPROFILE\Downloads\camera-map-alignment-home-test-001-home-camera-01.json"
~~~

実カメラ映像と位置を確認した後だけ、明示的に取り込みます：

~~~powershell
python .\import_map_alignment.py --config .\config.json --alignment "$env:USERPROFILE\Downloads\camera-map-alignment-home-test-001-home-camera-01.json" --apply --confirm-camera-view
~~~

カメラIDとJSONファイル名は実際の内容に読み替えてください。config_backup_map_alignment_日時.json が自動生成されます。YOLOは再起動すると新しい space_zones を使用します。公開設定・Supabase連携の設定は変更しません。

## 仕組みと注意

計算モジュールは camera-map-alignment-core.js。4点の対応から3×3射影行列の8未知数を求め、枠の中心回転を含む4頂点を変換します。レンズの歪みが大きい場合は、OpenCVなどで歪みを補正した画像を使用してください。

この変換は床面の平面上の点を対応させるもので、**車体や屋根の地面投影を正確に計測するものではありません**。YOLOの車両検出や「駐車中」の確定条件は従来どおりです。

カメラ移設、画角・クロップ変更、マップ全体の座標変更、高低差がある駐車場、床面が隠れている場合には再調整してください。誤った空き情報を出さないよう、録画で検証するまでは利用者向け公開を有効化しないでください。

## 検証

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin"
node --test tests/camera-map-alignment.test.cjs
cd .\parking-vision
python -m unittest discover -s tests -p "test_import_map_alignment.py"
~~~

このテストは射影変換と安全な取込みの**合成条件**を確認するものです。自宅駐車場6区画の実画像での正解率・位置一致は別途検証が必要です。
