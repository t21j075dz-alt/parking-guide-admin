# 管理者アプリ・カメラ処理のコード案内

## Web画面

| ファイル | 役割 |
| --- | --- |
| `index.html` | 画面構造とスクリプトの読み込み順 |
| `admin.js` / `admin.css` | マップ編集、区画設定、保存・同期と基本表示 |
| `admin-i18n.js` | 管理画面の翻訳 |
| `facility-catalog.js` / `facility-catalog.json` | 施設一覧のJavaScript版・JSON版 |
| `facility-editor.js` / `facility-operations.js` | 施設情報の編集と営業時間の判定 |
| `tenant-editor.js` | 複合施設内の店舗編集 |
| `editor-workbench.js` / `editor-workbench.css` | 編集操作の補助 |
| `admin-workspace-v2.js` / CSS | 施設選択と左右パネルの配置・開閉 |
| `workspace-refinement.js` / CSS | 機能検索、パネル内の閉じる操作、補足表示 |
| `admin-camera-shortcuts.js` / CSS | カメラ関連機能へのショートカット |
| `camera-view.js` | カメラ写真の取得・拡大表示 |
| `camera-map-alignment-core.js` | カメラとマップの座標変換 |
| `camera-map-alignment.js` / CSS | 位置合わせ画面 |
| `map-display.js` / CSS | マップ表示の共通処理 |
| `admin-voice.js` / `voice-speech-readings.js` | 音声の準備と読み方 |
| `recording-demo.js` | 録画実演の共有設定 |
| `sync-config.js` | 公開クライアントの接続設定 |
| `experience.css` | 画面の追加スタイル |

同名の利用者向けファイルでも内容や役割が異なる場合があります。特に`camera-view.js`には管理者だけの拡大操作があります。単純な重複と見なして片方を消さないでください。

## YOLO・カメラ処理（parking-vision）

| 処理 | 主なファイル |
| --- | --- |
| ライブ判定の入口 | `monitor.py` |
| カメラ選択・設定・録画 | `select_external_camera.py`, `camera_profiles.py`, `camera_exposure.py`, `camera_recording.py`, `setup_camo.py` |
| 輪郭・底面・区画判定 | `vehicle_segmentation.py`, `segmentation_quality.py`, `vehicle_zone.py`, `wheel_geometry.py`, `zone_geometry.py`, `parking_geometry_fusion.py` |
| 追跡・夜間・人物判定 | `stable_ids.py`, `night_vision.py`, `night_vehicle_evidence.py`, `person_stability.py` |
| 診断と評価 | `parking_diagnostics.py`, `person_diagnostics.py`, `compare_tracking.py`, `compare_vehicle_segmentation.py`, `evaluate_slots.py`, `analyze_video.py` |
| 座標登録・検証・移行 | `calibrate.py`, `import_map_alignment.py`, `verify_map_alignment.py`, `transfer_home_zones.py`, `reuse_live_zones_for_video.py` |
| 写真と判定映像 | `camera_snapshots.py`, `publish_camera.py`, `yolo_visual_recording.py` |
| 動画実演 | `video_replay.py`, `video_demo_support.py`, `prepare_video_demo.py`, `recorded_parking_states.py` |
| 道の駅日光の録画 | `nikko_video_config.py`, `import_nikko_map_alignment.py`, `export_nikko_recording.py` |
| 教師データ・学習 | `vehicle_mask_dataset.py`, `annotate_vehicle_masks.py`, `prepare_vehicle_mask_frames.py`, `train_vehicle_segmentation.py`, `label_obstacles.py`, `train_obstacles.py` |
| 実験・移行の補助 | `confirm_initial_empty.py`, `regenerate_lab_assets.py` |

`.ps1`と`.cmd`はWindowsから手動で実行する入口も含みます。他のプログラムから参照されていないことは、不要である証拠にはなりません。研究室PCの確認用`check_lab_pc.ps1`と、現地確認を記録する`confirm_initial_empty.ps1`も保持しています。詳細な実行条件は`parking-vision/README.md`と各スクリプト冒頭を確認してください。

## クラウド

`supabase/functions/parking-voice-prepare/index.ts`は音声準備のEdge Functionです。SQLファイルは初期構築・機能追加・権限設定の履歴を兼ねます。Web画面から直接読み込まれなくても、再構築に必要なので保持しています。今回の整理ではDB・認証・公開設定を変更していません。

## 変更後の確認

```sh
node scripts/check-source.cjs
node --test tests/*.test.cjs
node tests/ui-refinement-browser.cjs
node tests/camera-alignment-browser.cjs
python -m compileall -q parking-vision
cd parking-vision
python -m unittest discover -s tests -p 'test_*.py'
```

ブラウザーテストはPlaywrightとChromium、Pythonテストの一部はNumPyとOpenCVが必要です。GitHub ActionsではWindows PowerShell 5.1の構文も検査します。JavaScript・JSONの構文確認はファイル名の手作業列挙からGit管理下の全ファイル検査に変更しました。

## 2026-11-12の整理

未使用の変数・Python importと重複コメントを削除しました。カメラ表示、カメラ導線、施設・店舗編集、機能検索を複数行に整形し、整形前後のJavaScript構文木の一致を確認しました。車両判定の閾値や追跡方式は変更していません。

静的解析と自動テストの確認であり、全処理の正しさや実カメラ映像での検出精度を保証するものではありません。
