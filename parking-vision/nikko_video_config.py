#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道の駅日光の過去録画を仮想ライブカメラにする専用・安全な設定。

自宅実カメラの config.json は読み込むだけ。動画の区画位置は録画ごとに校正。
実際の施設の「現在の空き」と録画の状態は混ぜない。
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

FACILITY_ID = "nikko-test-001"
CAMERA_ID = "nikko-recording-01"
SPACE_UIDS = [f"space_{n:03d}" for n in range(1, 9)]
CONFIG_NAME = "config_nikko_video_demo.json"
SAFE_KEYS = (
    "supabase_url", "publishable_key", "vehicle_model", "obstacle_model",
    "confidence", "tracking_confidence", "tracker_file", "image_size",
    "park_seconds", "occupied_hold_seconds", "blocked_confirm_seconds",
    "reid_window_seconds", "night_vision_mode", "yolo_recording_fps",
    "recording_segment_seconds", "camera_preview_max_width",
    "camera_preview_max_height",
)


def read_settings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("設定ファイルはJSONオブジェクトで指定してください")
    return data


def make_config(base):
    if not isinstance(base, dict):
        raise ValueError("元のYOLO設定ファイルが不正です")
    missing = [name for name in ("vehicle_model", "supabase_url", "publishable_key")
               if not base.get(name)]
    if missing:
        raise ValueError("既存の設定に不足があります: " + ", ".join(missing))
    config = {key: deepcopy(base[key]) for key in SAFE_KEYS if key in base}
    config.update({
        "facility_id": FACILITY_ID,
        "camera_id": CAMERA_ID,
        "source": -1,  # 実カメラは絶対に開かない。
        "video_demo_only": True,
        "camera_verified_external": False,
        "camera_kind": "usb",
        "camera_snapshots_enabled": False,
        "public_snapshots_enabled": False,
        "allow_unverified_initial_empty": False,
        "initially_confirmed_empty_uids": [],
        "entry_zone": [],
        "exit_zone": [],
        "space_uids": SPACE_UIDS[:],
        "space_zones": {},
    })
    return config


def checked_config(config):
    if (config.get("facility_id") != FACILITY_ID or
            config.get("camera_id") != CAMERA_ID or
            config.get("video_demo_only") is not True):
        raise ValueError("日光の録画専用設定ではありません。既存のconfig.jsonは使用できません")
    if config.get("source") != -1 or config.get("camera_verified_external") is not False:
        raise ValueError("録画専用設定に実カメラの入力が混在しています")
    if config.get("camera_snapshots_enabled") or config.get("public_snapshots_enabled"):
        raise ValueError("録画モードでは写真をライブ公開できません")
    if config.get("allow_unverified_initial_empty"):
        raise ValueError("確認していない空き状態を初期設定には使えません")
    uids = config.get("space_uids")
    if uids != SPACE_UIDS:
        raise ValueError("道の駅日光はspace_001～space_008の8区画を指定してください")
    zones = config.get("space_zones")
    if not isinstance(zones, dict) or any(uid not in uids for uid in zones):
        raise ValueError("録画専用の区画IDに一致しない設定があります")
    return config


def video_signature(video):
    """巨大な動画も短時間で照合。容量と先頭・末尾1MiBのSHA-256を使用する。"""
    from video_replay import validate_video
    file = validate_video(video)
    length = file.stat().st_size
    digest = hashlib.sha256()
    digest.update(str(length).encode("ascii") + b"\0")
    with file.open("rb") as stream:
        digest.update(stream.read(1048576))
        if length > 1048576:
            stream.seek(max(0, length-1048576))
            digest.update(stream.read(1048576))
    return digest.hexdigest()


def checked_ready(config, video):
    """校正した動画そのものであること、8区画全ての登録を確かめる。"""
    checked_config(config)
    zones = config["space_zones"]
    if set(zones) != set(SPACE_UIDS):
        raise ValueError("8区画すべての四隅を先に校正してください")
    from zone_geometry import normalize_corners, audit_zones
    normalized = {}
    for uid in SPACE_UIDS:
        normalized[uid] = normalize_corners(zones[uid])
    if audit_zones(normalized):
        raise ValueError("登録区画が重なっています。動画の枠を登録し直してください")
    capture = config.get("recorded_calibration") or {}
    if capture.get("signature") != video_signature(video):
        raise ValueError(
            "この録画と区画登録時の動画が異なります。現在の動画で8区画を再設定してください"
        )
    if not (capture.get("width", 0) > 0 and capture.get("height", 0) > 0):
        raise ValueError("区画登録した動画の画像サイズが不明です。再設定してください")
    return normalized


def record_video_calibration(config, video, width, height):
    """calibrate.pyが保存直前にのみ呼ぶ。ファイルに直接書き込まない。"""
    checked_config(config)
    if min(width, height) <= 0:
        raise ValueError("録画の画像サイズを取得できません")
    config["recorded_calibration"] = {
        "signature": video_signature(video),
        "width": int(width),
        "height": int(height),
        "kind": "recorded_video",
    }
    return config


def ensure_file(base_path, output_path, model=""):
    output = Path(output_path).resolve()
    if output.is_file():
        return checked_config(read_settings(output)), False
    base = read_settings(base_path)
    config = make_config(base)
    if model:
        from pathlib import Path
        if not Path(model).is_file():
            raise ValueError("指定したYOLOモデルが見つかりません: " + model)
        config["vehicle_model"] = str(Path(model).resolve())
    with output.open("x", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return config, True


def main(argv=None):
    parser = argparse.ArgumentParser(description="道の駅日光・録画YOLO専用の設定を準備・確認")
    parser.add_argument("--base", default="config.json", help="既存の研究用設定（読み取りのみ）")
    parser.add_argument("--config", default=CONFIG_NAME, help="録画専用の出力・確認先")
    parser.add_argument("--video", default="", help="元動画のファイル名")
    parser.add_argument("--model", default="", help="新規作成時だけ独自YOLOモデルを指定")
    parser.add_argument("--check", action="store_true", help="8区画と録画の一致を検査")
    args = parser.parse_args(argv)
    if args.check:
        if not args.video:
            parser.error("--check には --video が必要です")
        config = read_settings(args.config)
        checked_ready(config, args.video)
        print("【一致】日光録画の8区画と動画の校正情報を確認しました。")
        return 0
    config, created = ensure_file(args.base, args.config, args.model)
    print(("【新規作成】" if created else "【既存設定を維持】") + str(Path(args.config).resolve()))
    print("【施設】道の駅日光・録画実験（実際の空きとは分離）")
    print("【対象】8区画／自宅用config.jsonには書き込みません")
    print("【モデル】" + str(config["vehicle_model"]))
    if args.model and not created:
        print("【注意】既存設定があるためモデルは変更しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
