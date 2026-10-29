#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自宅6区画の旧PC設定を動画デモ専用のconfigに取り込む。

現在のconfig.jsonは絶対に上書きせず、Supabase URL、公開キー、
ローカルの学習済みモデルパスはデスクトップ設定から保持する。
録画を実カメラと偽装しない。動画本体をクラウドへ送信しない。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from transfer_home_zones import read_settings, source_zones, camera_kind


DEMO_FACILITY = "home-video-demo-001"


def make_video_config(desktop, laptop):
    if desktop.get("facility_id") != "home-test-001":
        raise ValueError("デスクトップの元設定は home-test-001 である必要があります")
    ids, zones = source_zones(laptop)
    if camera_kind(laptop) != "usb":
        raise ValueError("今回はノートPCの外付けUSBカメラで撮影した動画用です")
    previous = laptop.get("calibration_capture") or {}
    if min(int(previous.get("width") or 0), int(previous.get("height") or 0)) <= 0:
        raise ValueError("移行元に校正時の映像解像度がありません")
    required = ["camera_id", "supabase_url", "publishable_key", "vehicle_model"]
    missing = [key for key in required if not desktop.get(key)]
    if missing:
        raise ValueError("デスクトップの設定項目が不足しています: " + ", ".join(missing))
    import copy
    config = copy.deepcopy(desktop)
    config["facility_id"] = DEMO_FACILITY
    config["camera_id"] = "home-video-demo-camera"
    config["space_uids"] = ids
    config["space_zones"] = zones
    config["entry_zone"] = laptop.get("entry_zone") or []
    config["exit_zone"] = laptop.get("exit_zone") or []
    config["camera_kind"] = "usb"
    config["calibration_capture"] = {
        "width": int(previous["width"]), "height": int(previous["height"]),
        "kind": "usb", "source": str(desktop.get("source", 0))
    }
    # This config is video-only; the actual source is always passed as --video.
    # A stale camera approval / empty-state approval must not become evidence.
    config["camera_verified_external"] = False
    config["initially_confirmed_empty_uids"] = []
    config.pop("initial_empty_verified_at", None)
    config["allow_unverified_initial_empty"] = False
    config["camera_snapshots_enabled"] = False
    config["public_snapshots_enabled"] = False
    return config


def main():
    parser = argparse.ArgumentParser(description="ノートPCの6区画から録画デモ設定を作成")
    parser.add_argument("--desktop", default="config.json")
    parser.add_argument("--laptop", default="config_from_laptop.json")
    parser.add_argument("--output", default="config_video_demo.json")
    args = parser.parse_args()
    desktop = Path(args.desktop).resolve()
    laptop = Path(args.laptop).resolve()
    output = Path(args.output).resolve()
    if output in (desktop, laptop):
        raise SystemExit("【中止】入力ファイルへの上書きは禁止です")
    old = read_settings(laptop)
    settings = make_video_config(read_settings(desktop), old)
    if output.exists():
        backup = output.with_name(
            "config_video_demo_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
        )
        shutil.copy2(output, backup)
        print(f"【バックアップ】{backup.name}")
    output.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"【作成完了】{output}")
    print("【施設】自宅の実ライブとは別の録画実演専用施設")
    print("【駐車枠】6区画・入口・出口を引き継ぎました")
    print("【モデル】現在のデスクトップPCの学習済みモデルの保存先を維持します")
    print("【注意】動画の撮影角度が異なれば、区画線は再登録が必要です")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"【設定作成中止】{exc}")
