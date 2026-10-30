#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""録画用の区画設定へ、同じ画角で登録したリアルタイムカメラの6区画を流用する。

前提：動画と元カメラの撮影位置・向き・画角が同じ。
Supabaseへの送信をせず、動画への枠の重ね合わせをSで承認するまで保存しない。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

from transfer_home_zones import camera_kind, read_settings, source_zones
from zone_geometry import normalize_corners
from camera_profiles import assert_calibrated_view
from video_demo_support import verify_overlay_with_operator

HERE = Path(__file__).resolve().parent
DEMO_FACILITY = "home-video-demo-001"


def make_settings(source: dict, target: dict, zones: dict, uids: list[str],
                  width: int, height: int) -> dict:
    """実カメラの認証・承認・入力番号を録画へ引き継がない。"""
    settings = dict(target)
    if settings.get("facility_id") != DEMO_FACILITY:
        raise ValueError("コピー先は録画実演施設 home-video-demo-001 に限ります")
    if set(settings.get("space_uids") or []) != set(uids):
        raise ValueError("録画用施設の区画IDとカメラ区画IDが一致しません")
    kind = camera_kind(source)
    settings["space_uids"] = uids
    settings["space_zones"] = zones

    for field in ("entry_zone", "exit_zone"):
        value = source.get(field) or []
        settings[field] = normalize_corners(value) if value else []

    # -1は録画専用のダミー番号。monitor.pyには--videoでMP4を渡す。
    # カメラを実際に確認したというフラグは継承しない。
    settings["source"] = -1
    settings["camera_kind"] = kind
    settings["camera_verified_external"] = False
    settings["initially_confirmed_empty_uids"] = []
    settings.pop("initial_empty_verified_at", None)
    settings.pop("initial_empty_valid_seconds", None)
    settings["allow_unverified_initial_empty"] = False
    settings["camera_snapshots_enabled"] = False
    settings["public_snapshots_enabled"] = False

    # 動画の表示確認後の実寸で記録し、別縦横比の画像には使えないようにする。
    settings["calibration_capture"] = {
        "width": width,
        "height": height,
        "source": str(settings["source"]),
        "kind": kind,
        "origin": "verified_recorded_video",
    }
    assert_calibrated_view(settings, width, height)
    return settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="実カメラで登録した駐車区画を、同画角の動画実演に流用する"
    )
    parser.add_argument(
        "--source-config", default=str(HERE / "config_usb_original.json"),
        help="元の6区画が入ったconfig.json等",
    )
    parser.add_argument(
        "--demo-config", default=str(HERE / "config_video_demo.json"),
        help="既存の録画実演用設定（勝手には生成しません）",
    )
    parser.add_argument("--video", required=True, help="元の未加工MP4")
    args = parser.parse_args()

    src = Path(args.source_config).expanduser().resolve()
    dst = Path(args.demo_config).expanduser().resolve()
    video = Path(args.video).expanduser().resolve()
    if not src.is_file():
        raise ValueError(f"コピー元の設定がありません: {src}")
    if not dst.is_file():
        raise ValueError(f"録画用設定がありません: {dst}")
    if not video.is_file():
        raise ValueError(f"録画元の動画がありません: {video}")
    if src == dst:
        raise ValueError("コピー元とコピー先を同一にできません")

    source = read_settings(src)
    target = read_settings(dst)
    uids, polygons = source_zones(source)
    if set(uids) != {f"space_{n:03d}" for n in range(1, 7)}:
        raise ValueError("既存の6区画(space_001〜006)を確認してください")
    if camera_kind(source) not in ("usb", "camo"):
        raise ValueError("元設定のカメラ種別が不明です。設定を確認してください")
    if target.get("facility_id") != DEMO_FACILITY:
        raise ValueError("録画用施設以外は変更しません")
    if set(target.get("space_uids") or []) != set(uids):
        raise ValueError("録画用施設の区画IDが移行元と異なります")

    import cv2
    camera = cv2.VideoCapture(str(video))
    try:
        ok, frame = camera.read()
    finally:
        camera.release()
    if not ok or frame is None:
        raise ValueError(f"動画の最初のフレームを読み取れません: {video}")
    height, width = frame.shape[:2]

    metadata = source.get("calibration_capture") or {}
    previous_width = int(metadata.get("width") or 0)
    previous_height = int(metadata.get("height") or 0)
    print("===== 録画用：リアルタイム区画の流用 =====")
    print(f"コピー元：{src.name} （{len(uids)}区画）")
    print(f"動画：{video.name} / {width} x {height}")
    if min(previous_width, previous_height) > 0:
        print(f"元カメラの区画登録時：{previous_width} x {previous_height}")
        if abs(width / height - previous_width / previous_height) > 0.025:
            raise ValueError(
                "元カメラと動画の縦横比が異なります。既存の区画を流用せず、"
                "録画用のcalibrate.pyで再登録してください"
            )
    else:
        print("【注意】元カメラの解像度記録がないため自動照合できません。")

    settings = make_settings(source, target, polygons, uids, width, height)
    model = Path(str(settings.get("vehicle_model") or ""))
    if not model.is_file():
        print(f"【注意】録画用のvehicle_modelが見つかりません：{model}")
        print("区画のコピーは可能ですが、実行前にモデルのパスを修正してください。")

    print("")
    print("【重要】動画と元カメラの撮影位置・角度・ズームが同じ場合だけ流用できます。")
    print("表示される枠が6区画すべてに重なっていればS、ずれたらQを押してください。")
    if not verify_overlay_with_operator(frame, polygons, cv2):
        print("【中止】区画のコピーは行っていません。元データも変更していません。")
        return

    # 明示承認した場合だけ既存ファイルをバックアップして更新する。
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = dst.with_name(f"{dst.stem}_backup_before_zone_reuse_{stamp}{dst.suffix}")
    if backup.exists():
        raise ValueError(f"バックアップ先が存在します: {backup}")
    shutil.copy2(dst, backup)
    dst.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"[OK] 録画専用設定に6区画を反映: {dst}")
    print(f"[OK] 変更前設定のバックアップ: {backup}")
    print("実カメラの設定とSupabaseのデータは変更していません。")
    print("録画を実ライブとして送信することはできません。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"【中止】{exc}")
