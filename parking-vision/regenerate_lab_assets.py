#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研究室PCで標準YOLOと新しい実験設定を安全に生成する。

- 以前の独自学習済みbest.ptは復元しない
- データベースへの書き込み・録画共有はしない
- 既存の設定ファイルと独自学習済みモデルを上書きしない
- 撮影範囲は映像で手動登録するまで空欄のままにする
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
HOME = Path.home()
RESEARCH = HOME / "parking-vision"
WEIGHTS = RESEARCH / "weights"
BASELINE = WEIGHTS / "baseline_yolo11n.pt"
EXAMPLE = HERE / "config.example.json"
SYNC_CONFIG = HERE.parent / "sync-config.js"
# 2026-10-30、実験施設の既存レイアウトに登録されていた6区画。
# 管理者アプリで区画IDを変更した場合は再確認する。
EXPERIMENT_SPACE_UIDS = [f"space_{number:03d}" for number in range(1, 7)]


def load_public_connection() -> tuple[str, str]:
    """既存アプリの公開用Supabase接続情報だけを読み取る。"""
    if not SYNC_CONFIG.is_file():
        raise RuntimeError(f"接続設定がありません: {SYNC_CONFIG}")
    content = SYNC_CONFIG.read_text(encoding="utf-8-sig")
    url_match = re.search(r'supabaseUrl:\s*["\']([^"\']+)["\']', content)
    key_match = re.search(r'publishableKey:\s*["\']([^"\']+)["\']', content)
    if not url_match or not key_match:
        raise RuntimeError("sync-config.jsから公開用接続設定を取得できません")
    url, key = url_match.group(1), key_match.group(1)
    if not re.fullmatch(r"https://[a-z0-9-]+\\.supabase\\.co", url):
        raise RuntimeError("Supabase URLの形式を確認してください")
    if not key.startswith("sb_publishable_"):
        raise RuntimeError("公開用キーの形式を確認してください。秘密鍵は使用できません")
    return url, key


def prepare_baseline() -> Path:
    """初期YOLO11nモデルを取得。以前のbest.ptとは別のファイルにする。"""
    WEIGHTS.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO

    if BASELINE.is_file():
        YOLO(str(BASELINE))
        print(f"[OK] 標準YOLOモデルは準備済み: {BASELINE}")
        return BASELINE

    print("[実行] 標準YOLO11nを取得します（初回はインターネットが必要）")
    # YOLOが必要に応じて公式配布の学習済み標準モデルを取得する。
    local = HERE / "yolo11n.pt"
    YOLO(str(local) if local.is_file() else "yolo11n.pt")
    if not local.is_file():
        raise RuntimeError(
            "yolo11n.ptが取得できません。ネット接続とYOLOの出力を確認してください。"
        )
    shutil.copy2(local, BASELINE)
    YOLO(str(BASELINE))
    print(f"[新規作成] 標準YOLOモデル: {BASELINE}")
    return BASELINE


def create_settings(filename: str, facility: str, camera: str,
                    url: str, public_key: str, model_path: Path) -> None:
    path = HERE / filename
    if path.exists():
        print(f"[保護] 既存の設定を変更しません: {path.name}")
        return

    settings = json.loads(EXAMPLE.read_text(encoding="utf-8-sig"))
    settings.update({
        "facility_id": facility,
        "camera_id": camera,
        "supabase_url": url,
        "publishable_key": public_key,
        "vehicle_model": str(model_path),
        "obstacle_model": "",
        "source": -1,
        "camera_verified_external": False,
        "camera_kind": "usb",
        "space_uids": EXPERIMENT_SPACE_UIDS,
        "space_zones": {},
        "entry_zone": [],
        "exit_zone": [],
        "initially_confirmed_empty_uids": [],
        "allow_unverified_initial_empty": False,
        "camera_snapshots_enabled": False,
        "public_snapshots_enabled": False,
        "image_size": 640,
    })
    # Python json.loadが確実に読めるよう、UTF-8 BOMなしで保存する。
    text = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(text)
    print(f"[新規作成] {path.name}")
    print("  区画座標は未登録です。対象の映像を見ながら必ず登録してください。")


def main() -> None:
    print("===== 研究室PC：研究素材の新規生成 =====")
    print("これは以前の学習済みbest.ptを復元する操作ではありません。")
    print("既存設定の上書き・Supabaseへの書き込み・映像共有はしません。")
    if not EXAMPLE.is_file():
        raise RuntimeError(f"初期テンプレートがありません: {EXAMPLE}")

    url, key = load_public_connection()
    model = prepare_baseline()
    create_settings("config_video_demo.json", "home-video-demo-001",
                    "home-video-demo-camera", url, key, model)
    create_settings("config.json", "home-test-001",
                    "home-camera-01", url, key, model)

    print("")
    print("===== 次に必要な操作 =====")
    print("1. 録画ループ：元の未加工MP4を用意し、calibrate.pyで6区画を登録。")
    print("2. USBカメラ：select_external_camera.pyで実物を目視確認し、枠を登録。")
    print("3. Camo：iPhone接続後、start.ps1 -Mode camo-setupで専用設定を作る。")
    print("4. 新規作成したモデルは標準YOLO11nです。旧best.ptとの精度比較は別条件。")
    print("5. 初期設定の枠ID6件が管理者アプリの現在の施設と一致するか確認。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"[中止] {exc}")
