#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自宅用の実カメラ監視設定を、既存の録画設定から安全に作成する。

既存config.jsonは変更しない。実カメラと録画で画角が違う可能性があるため
デフォルトでは登録済みの枠座標を流用しない。
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path

from admin_layout import read_export

HOME_ID = "home-test-001"
SUPPORTED = {"source", "space_zones", "space_uids", "facility_id", "camera_id"}


def prepare_home_config(source: dict, camera: int | str = 0, *,
                        reuse_camera_geometry: bool = False,
                        layout=None) -> dict:
    if source.get("facility_id") != HOME_ID:
        raise ValueError(
            f"自宅用設定の元データは {HOME_ID} のみ使用できます。"
            " 日光など他施設の座標は取り込まないでください。"
        )
    camera = int(camera) if str(camera).isdigit() else camera
    if isinstance(camera, str) and Path(camera).suffix.lower() in {
        ".mp4", ".mov", ".avi", ".mkv", ".webm"
    }:
        raise ValueError("ライブカメラには録画ファイルを指定できません")
    config = copy.deepcopy(source)
    config["source"] = camera
    config["camera_id"] = "home-live-camera-01"
    config["allow_unverified_initial_empty"] = False
    config["initially_confirmed_empty_uids"] = []
    config["verify_admin_layout_on_cloud"] = True
    config["parking_stay_tracking"] = True
    config["camera_blind_space_uids"] = []
    config["occluded_by_spaces"] = {}
    config["monitored_site_polygon"] = []
    config["occupied_hold_seconds"] = 8
    config["park_seconds"] = max(3, float(config.get("park_seconds", 5)))
    config["tracking_confidence"] = .15
    config["confidence"] = max(.25, float(config.get("confidence", .35)))
    if not reuse_camera_geometry:
        config["space_zones"] = {}
        config["entry_zone"] = []
        config["exit_zone"] = []
    if layout:
        from admin_layout import extract
        from_layout = extract(layout, HOME_ID)
        config["space_uids"] = sorted(from_layout)
        # 注意：管理画面の地図上の座標はカメラの座標に変換できない
        invalid_zones = sorted(set(config["space_zones"]) - set(from_layout))
        if invalid_zones:
            raise ValueError("管理者レイアウトにない枠UID: " + ", ".join(invalid_zones))
    return config


def main():
    parser = argparse.ArgumentParser(description="自宅駐車場の実カメラ用config作成")
    parser.add_argument("--from-config", required=True,
                        help="既存の自宅用config.json。元ファイルは変更しません")
    parser.add_argument("--output", default="config_home_live.json")
    parser.add_argument("--camera", default="0", help="USBカメラ番号0、または許可済みRTSP URL")
    parser.add_argument("--admin-layout", help="管理アプリから書き出したparking-layouts.json")
    parser.add_argument("--reuse-camera-geometry", action="store_true",
                        help="前と同じ固定カメラ・同じ画角と確認した場合のみ使う")
    args = parser.parse_args()
    original = Path(args.from_config).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not original.is_file():
        parser.error("以前の自宅config.jsonがありません")
    if output == original:
        parser.error("元のconfig.jsonは上書きしません。--outputは別名にしてください")
    if output.exists():
        parser.error(f"出力先が既に存在します。誤上書きを避けるため別名にしてください: {output}")
    source = json.loads(original.read_text(encoding="utf-8-sig"))
    layout = json.loads(Path(args.admin_layout).read_text(encoding="utf-8-sig")) if args.admin_layout else None
    prepared = prepare_home_config(
        source, args.camera,
        reuse_camera_geometry=args.reuse_camera_geometry,
        layout=layout,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("自宅用カメラ設定を作成:", output)
    print("敷地/駐車枠:", len(prepared.get("space_zones", {})), "区画")
    print("録画と画角が異なる場合はcalibrate.pyで区画を再登録してください。")
    print("管理者が実際に確認するまで利用者アプリには公開しないでください。")


if __name__ == "__main__":
    main()
