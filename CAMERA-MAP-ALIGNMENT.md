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

## 第2段階：実カメラで区画の重ね合わせを確認する（2026-11-06）

位置合わせを一度保存すると、次回は4点を再選択しなくても、カメラ写真を読み込んだ時点で**現在の管理マップから全区画を自動再計算**します。駐車枠の位置や回転が変更されていれば注意を表示します。変更のたびにYOLO側で四隅を登録する必要はありません。

ただし、再計算だけでは精度を保証できません。管理アプリでは画像上の**すべての区画が合うことをチェック**するまで、JSON書き出しは無効です。確認した4点・カメラ縦横比・マップ配置署名を端末に保存します。マップの大きさやカメラの縦横比が変わった場合は4点の再登録を求めます。

### 推奨の実機確認手順

1. GitHubの main を取得して管理アプリで位置合わせを行い、JSONを保存する。
2. カメラを占有する既存のYOLO・Camo配信等を停止。カメラは元の位置に固定する。
3. PCの parking-guide-admin\parking-vision\カメラとマップの位置合わせを確認.cmd をダブルクリック。JSONをドラッグしてパスを指定できる。
4. カメラ映像に全区画の線が描かれる。SPACE で静止し、実際の白線と番号が合っているかすべて確認する。
5. 合わなければ Q で中止。合っていれば V を押すと camera-map-verified-日時.json を元JSONの隣へ生成する。
6. **録画動画の --video モードでは検証記録を出力できません**。実カメラからの確認が必要です。
7. この段階ではまだYOLO・Supabaseの設定変更はありません。

PowerShellから実行する場合：

~~~powershell
cd "$env:USERPROFILE\parking-guide-admin\parking-vision"
python .\verify_map_alignment.py --config .\config.json --alignment "C:\Users\Owner\Downloads\camera-map-alignment-home-test-001-home-camera-01.json"
~~~

※ JSONのパスは実際に出力したファイルを指定してください。研究室PCなどユーザー名が異なる場合は適宜変更します。

### 実カメラ確認後の安全な反映

~~~powershell
# 書き換えない事前確認
python .\import_map_alignment.py --config .\config.json --alignment "C:\...\camera-map-alignment-....json" --verification "C:\...\camera-map-verified-....json"

# 全区画の位置を確認した場合のみ、バックアップ作成とともに反映
python .\import_map_alignment.py --config .\config.json --alignment "C:\...\camera-map-alignment-....json" --verification "C:\...\camera-map-verified-....json" --apply
~~~

位置合わせJSONと確認記録は同じ組み合わせにしてください。別の区画JSONに差し替えた場合、ハッシュの不一致で拒否します。カメラ番号・カメラ種類・施設ID・区画一覧・撮影縦横比の不一致でも反映されません。確認記録は7日間有効ですが、カメラが動いた場合は直ちに再確認が必要です。

新しい確認記録を使った反映時には、実カメラで確認された解像度とカメラ入力元を calibration_capture へ保存します。通常起動時の画角違いの検出に使用します。暗所、レンズ歪み、カメラを動かした後に縦横比だけが同じ場合は**自動では判別できません**。

### 検証できる範囲・できない範囲

- 自動テストは射影変換、マップ変更後の再計算、撮影縦横比の不一致、確認記録の改変、期限切れ、施設・カメラID不一致、バックアップ作成を検証します。
- 実カメラの白線位置まで自動検出して最適化する機能ではありません。対応点の初回指定は必要です。
- OpenCVでの重ね合わせは駐車区画の**位置の確認**であって、車両の満空判定ではありません。判定結果を変更することはありません。
