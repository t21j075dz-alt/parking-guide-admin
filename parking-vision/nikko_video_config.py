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
import re
from datetime import datetime
import shutil

FACILITY_ID = "nikko-test-001"
CAMERA_ID = "nikko-recording-01"
MAX_VISIBLE_SPACES = 999
UID_PATTERN = re.compile(r"space_[A-Za-z0-9_-]{1,40}\Z")
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




def visible_space_uids(space_count=0, space_uids=""):
    """画角内の区画のみを登録。番号は管理者マップと同じにできる。"""
    if space_count and space_uids:
        raise ValueError("区画数と区画IDの直接指定は併用できません")
    if space_uids:
        ids = [x.strip() for x in space_uids.split(",")]
    elif 1 <= space_count <= MAX_VISIBLE_SPACES:
        ids = [f"space_{number:03d}" for number in range(1, space_count + 1)]
    else:
        raise ValueError("映像内の区画数を1～999で指定してください。例: --space-count 24")
    if (not ids or len(ids) > MAX_VISIBLE_SPACES or
            len(ids) != len(set(ids)) or
            not all(UID_PATTERN.fullmatch(uid) for uid in ids)):
        raise ValueError("駐車区画IDが重複、または形式が不正です")
    return ids

def make_config(base, space_uids):
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
        "space_uids": list(space_uids),
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
    if (not isinstance(uids, list) or not 1 <= len(uids) <= MAX_VISIBLE_SPACES
            or len(set(uids)) != len(uids)
            or not all(isinstance(uid, str) and UID_PATTERN.fullmatch(uid) for uid in uids)):
        raise ValueError("道の駅日光で撮影範囲に入る区画だけを1～999件登録してください")
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
    """校正した動画そのもの・撮影範囲内の登録区画を確認。"""
    checked_config(config)
    zones = config["space_zones"]
    ids = config["space_uids"]
    if set(zones) != set(ids):
        missing = sorted(set(ids) - set(zones))
        raise ValueError(
            "撮影範囲内の区画をすべて校正してください。未登録: " + ", ".join(missing[:12])
        )
    from zone_geometry import normalize_corners, audit_zones
    normalized = {}
    for uid in ids:
        normalized[uid] = normalize_corners(zones[uid])
    warnings = audit_zones(normalized)
    if any("重なって" in warning for warning in warnings):
        raise ValueError("登録区画が重なっています。動画の枠を登録し直してください")
    for warning in warnings:
        print("【映像内の区画に注意】" + warning)
    capture = config.get("recorded_calibration") or {}
    if capture.get("signature") != video_signature(video):
        raise ValueError(
            "この録画と区画登録時の動画が異なります。現在の動画で撮影範囲内の区画を再設定してください"
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


def ensure_file(base_path, output_path, model="", ids=None, reset=False):
    """現地用config.jsonに書き込まない。変更時は必ず録画設定をバックアップ。"""
    output = Path(output_path).resolve()
    base = Path(base_path).resolve()
    if output == base:
        raise ValueError("実カメラの元設定への上書きは禁止です")
    if output.is_file() and not reset:
        current = checked_config(read_settings(output))
        if ids is not None and ids != current["space_uids"]:
            raise ValueError(
                "登録済みの対象区画が違います。変更する場合のみ --reset-zones を指定してください"
            )
        return current, False
    if not ids:
        raise ValueError("最初に画角内の駐車区画数を指定してください（--space-count）")
    existing = checked_config(read_settings(output)) if output.is_file() else None
    if existing is not None:
        # 旧カメラ設定や登録済みの校正範囲を誤って消さない。
        if not reset:
            raise ValueError("既存の録画設定を上書きできません")
        if model:
            raise ValueError("区画変更とYOLOモデル変更を同時には行えません")
        original = deepcopy(existing)
        original["space_uids"] = list(ids)
        original["space_zones"] = {}
        original.pop("recorded_calibration", None)
        new = original
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = output.with_name(output.stem + "_backup_" + stamp + ".json")
        shutil.copy2(output, backup)
        print("【バックアップ】" + str(backup))
    else:
        new = make_config(read_settings(base), ids)
        if model:
            if not Path(model).is_file():
                raise ValueError("指定したYOLOモデルが見つかりません: " + model)
            new["vehicle_model"] = str(Path(model).resolve())
    # テスト用の既存設定を保護し、新規はxモードで排他作成。
    with output.open("w" if existing else "x", encoding="utf-8") as stream:
        json.dump(new, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return new, True


def main(argv=None):
    parser = argparse.ArgumentParser(description="道の駅日光・録画YOLO専用の設定を準備・確認")
    parser.add_argument("--base", default="config.json", help="既存の研究用設定（読み取りのみ）")
    parser.add_argument("--config", default=CONFIG_NAME, help="録画専用の出力・確認先")
    parser.add_argument("--video", default="", help="元動画のファイル名")
    parser.add_argument("--model", default="", help="新規作成時だけ独自YOLOモデルを指定")
    parser.add_argument("--space-count", type=int, default=0,
                        help="映像に映る駐車区画数（1～999。8件固定ではありません）")
    parser.add_argument("--space-uids", default="",
                        help="管理マップの区画IDを指定（カンマ区切り。画角外は指定しない）")
    parser.add_argument("--reset-zones", action="store_true",
                        help="区画数の変更時にバックアップ後、日光録画用の校正だけ消す")
    parser.add_argument("--check", action="store_true", help="すべての映像内区画と録画の一致を検査")
    args = parser.parse_args(argv)
    if args.check:
        if not args.video:
            parser.error("--check には --video が必要です")
        config = read_settings(args.config)
        checked_ready(config, args.video)
        print(f"【一致】日光録画の{len(config['space_uids'])}区画と校正情報を確認しました。")
        return 0
    ids = (visible_space_uids(args.space_count, args.space_uids)
           if args.space_count or args.space_uids else None)
    config, created = ensure_file(args.base, args.config, args.model, ids,
                                  reset=args.reset_zones)
    print(("【作成・更新完了】" if created else "【既存設定を維持】") + str(Path(args.config).resolve()))
    print("【施設】道の駅日光・録画実験（実際の空きとは分離）")
    print(f"【判定対象】画角内の{len(config['space_uids'])}区画だけ／画角外は含みません")
    print("【区画ID】" + ", ".join(config["space_uids"]))
    print("【モデル】" + str(config["vehicle_model"]))
    if args.model and not created:
        print("【注意】既存設定があるためモデルは変更しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
