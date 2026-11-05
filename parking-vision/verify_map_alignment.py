#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実カメラに管理マップから生成した全区画を重ね、目視承認した記録を保存する。

表示中は実カメラ・YOLO設定・クラウドへの書込みを一切行わない。
SPACEで静止 → Vで承認すると、取込用の検証記録JSONのみ作成する。
録画動画(--video)はプレビュー専用であり、実カメラ確認の代用にしない。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from import_map_alignment import checked_alignment, read_json


def alignment_digest(path):
    """厳密に同一の書き出しJSONだけが検証済みと判断されるよう生バイトで計算。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_camera_frame(config, alignment, width, height):
    if min(int(width), int(height)) <= 0:
        raise ValueError("カメラから有効な画像を取得できません")
    expected = float(alignment["image_width"]) / float(alignment["image_height"])
    actual = width / height
    # 画角が違うと正規化座標の枠もずれる。解像度の変更だけは許容する。
    if abs(actual / expected - 1.0) > 0.015:
        raise ValueError(
            f"位置合わせ写真とカメラ映像の縦横比が異なります"
            f"（登録時 {alignment['image_width']}x{alignment['image_height']}、"
            f"現在 {width}x{height}）。設定を確認してください。"
        )
    if config.get("facility_id") == "home-test-001":
        if not isinstance(config.get("source"), int) or config.get("source") < 0:
            raise ValueError("自宅駐車場では確認済みの外付けカメラ番号を使用してください")
        if config.get("camera_verified_external") is not True:
            raise ValueError("外付けUSB/Camoカメラが目視確認済みである必要があります")


def preview_frame(frame, zones, cv2):
    """現在の実映像に監視対象の四辺形を重ねる。判定結果ではなく設定確認のみ。"""
    height, width = frame.shape[:2]
    view = frame.copy()
    fill = frame.copy()
    for zone in zones.values():
        points = cv2.UMat if False else None  # OpenCV以外のモジュールに依存しない
        import numpy as np
        points = np.array([[round(x * (width - 1)), round(y * (height - 1))]
                           for x, y in zone], dtype=np.int32)
        cv2.fillConvexPoly(fill, points, (70, 190, 80), lineType=cv2.LINE_AA)
    cv2.addWeighted(fill, .22, view, .78, 0, dst=view)
    for uid, zone in zones.items():
        import numpy as np
        pts = np.array([[round(x * (width - 1)), round(y * (height - 1))]
                        for x, y in zone], dtype=np.int32)
        cv2.polylines(view, [pts], True, (75, 245, 100), 2, cv2.LINE_AA)
        cx, cy = [int(round(sum(point[axis] for point in pts) / len(pts)))
                  for axis in range(2)]
        number = uid.removeprefix("space_").lstrip("0") or uid
        cv2.putText(view, "SPACE " + number, (max(0, cx - 35), max(18, cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, .52, (8, 35, 15), 3, cv2.LINE_AA)
        cv2.putText(view, "SPACE " + number, (max(0, cx - 35), max(18, cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1, cv2.LINE_AA)
    return view


def build_receipt(config, alignment, alignment_path, frame_width, frame_height):
    assert_camera_frame(config, alignment, frame_width, frame_height)
    checked_alignment(config, alignment)
    return {
        "schema_version": 1,
        "facility_id": config["facility_id"],
        "camera_id": config["camera_id"],
        "camera_source": config["source"],
        "camera_kind": str(config.get("camera_kind", "usb")).lower(),
        "image_width": int(frame_width),
        "image_height": int(frame_height),
        "space_uids": alignment["space_uids"],
        "alignment_sha256": alignment_digest(alignment_path),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "confirmation": "fixed-camera-live-view-manually-approved",
    }


def write_receipt(path, receipt):
    """検証記録は既存config.jsonとは別ファイルに保存する。"""
    path = Path(path)
    if path.exists():
        raise FileExistsError("検証記録が既に存在します。別の名前で保存してください。")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="実カメラ上で区画の自動投影を確認する")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--alignment", required=True, help="管理者アプリから出力したJSON")
    parser.add_argument("--video", default="", help="実験動画で表示だけ確認（承認記録は生成しない）")
    args = parser.parse_args(argv)
    config = read_json(args.config)
    alignment = read_json(args.alignment)
    zones = checked_alignment(config, alignment)

    import cv2
    from camera_profiles import capture_preferences, fit_preview_dimensions
    from camera_recording import open_camera
    if args.video:
        # 動画は現在のカメラとの一致を証明できない。
        source = str(Path(args.video).expanduser().resolve())
        if not Path(source).is_file():
            raise ValueError("動画ファイルが見つかりません")
    else:
        source = config.get("source")
        if not isinstance(source, int) or source < 0 or config.get("camera_verified_external") is not True:
            raise ValueError("カメラを確認してからライブプレビューを実行してください")
    width, height, fps = capture_preferences(config)
    cam = open_camera(
        cv2, source, config.get("camera_backend", "auto"),
        config.get("camera_manual_exposure"),
        width if not args.video else 0,
        height if not args.video else 0,
        fps if not args.video else 0,
    )
    if not cam.isOpened():
        cam.release()
        raise ValueError("カメラ映像を取得できません")
    print("【安全】映像と枠の位置を比較するだけです。YOLO/Supabaseは更新しません。")
    print("【操作】SPACE: 静止・再生 / V: 静止したカメラ画像を確認して記録 / Q・Esc: 終了")
    if args.video:
        print("【録画モード】映像の確認だけです。承認記録は作成できません。")
    window="Parking map -> live camera alignment / SPACE pause / V confirm"
    frozen=False
    raw=None
    try:
        while True:
            if not frozen:
                ok, capture = cam.read()
                if not ok:
                    if args.video:
                        break
                    raise ValueError("カメラ映像の取得が途切れました。位置合わせを中止します")
                raw=capture
            frame_height, frame_width=raw.shape[:2]
            assert_camera_frame(config, alignment, frame_width, frame_height)
            display=preview_frame(raw, zones, cv2)
            display_width, display_height=fit_preview_dimensions(
                frame_width, frame_height, 1280, 800)
            if (display_width,display_height)!=(frame_width,frame_height):
                display=cv2.resize(display,(display_width,display_height),
                                   interpolation=cv2.INTER_AREA)
            cv2.putText(display, "PAUSED - check EVERY parking space" if frozen
                        else "LIVE - SPACE to pause", (12, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, (255,255,255), 2, cv2.LINE_AA)
            cv2.imshow(window, display)
            key=cv2.waitKey(30) & 0xFF
            if key in (27,ord("q"),ord("Q")):
                print("【終了】位置合わせの設定は変更していません。")
                return 0
            if key==32:
                frozen=not frozen
            elif key in (ord("v"),ord("V")):
                if args.video:
                    print("【不可】録画だけでは現在のカメラ角度を確認できません。")
                elif not frozen:
                    print("【確認】SPACEで現在の画像を静止してから、全区画を目視確認してください。")
                else:
                    receipt=build_receipt(config,alignment,args.alignment,
                                          frame_width,frame_height)
                    stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
                    target=Path(args.alignment).resolve().with_name(
                        "camera-map-verified-"+stamp+".json")
                    write_receipt(target, receipt)
                    print("【保存】実カメラとの位置合わせ確認記録:",target)
                    print("【次の操作】import_map_alignment.py の --verification に指定できます。")
                    return 0
        print("【録画終了】実カメラの設定は変更していません。")
        return 0
    finally:
        cam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
