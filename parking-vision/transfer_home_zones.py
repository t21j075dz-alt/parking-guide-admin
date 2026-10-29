#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ノートPCで登録した6駐車区画を、デスクトップの実カメラで照合して引き継ぐ。

安全条件:
- 既存config.jsonと元設定の施設IDが同じhome-test-001である。
- 4点の区画がすべて登録され、UIDが重複していない。
- デスクトップに接続した外付けカメラが目視確認済みである。
- カメラ画面に重ねた枠が実際の区画に一致し、利用者が明示承認する。
- 設定変更前に必ずバックアップを取り、カメラ番号と画角メタデータを
  *デスクトップ側* の値に更新する。秘密鍵・映像は転送しない。
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import shutil

from camera_profiles import assert_calibrated_view, capture_preferences
from zone_geometry import audit_zones, normalize_corners


EXPECTED_FACILITY = "home-test-001"
DEFAULT_BACKUP = "config_backup_desktop_before_camera.json"


def read_settings(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def zone_inventory(settings):
    """Return safe diagnostic metadata. Never print cloud credentials or geometry."""
    if not isinstance(settings, dict):
        return {"facility": False, "ids": 0, "polygons": 0,
                "valid_polygons": 0, "complete": False}
    ids = settings.get("space_uids")
    ids = list(ids) if isinstance(ids, list) else []
    polygons = settings.get("space_zones") or {}
    polygons = polygons if isinstance(polygons, dict) else {}
    valid = 0
    for points in polygons.values():
        try:
            normalize_corners(points)
            valid += 1
        except (ValueError, TypeError):
            pass
    expected = {f"space_{i:03d}" for i in range(1, 7)}
    keys = set(map(str, polygons))
    id_set = set(map(str, ids))
    return {
        "facility": settings.get("facility_id") == EXPECTED_FACILITY,
        "ids": len(ids),
        "polygons": len(polygons),
        "valid_polygons": valid,
        "complete": (
            settings.get("facility_id") == EXPECTED_FACILITY
            and keys == expected and valid == 6
            and (id_set == expected or len(ids) < 6)
        ),
    }


def source_zones(source):
    """Use only all six verified camera polygons, never fabricate missing ones.

    Older setups may contain all six space_zones but only one space_uid
    after a 'quick setup'. Canonical six IDs may be recovered in that case
    because the actual polygons are present and will be visually checked.
    """
    if source.get("facility_id") != EXPECTED_FACILITY:
        raise ValueError("移行元が自宅駐車場の設定ではありません")
    zone_ids = list(map(str, source.get("space_uids") or []))
    polygons = source.get("space_zones") or {}
    expected = [f"space_{i:03d}" for i in range(1, 7)]
    if not isinstance(polygons, dict):
        raise ValueError("カメラの区画座標が正しい形式ではありません")
    if len(zone_ids) == 6 and len(set(zone_ids)) == 6:
        if set(polygons) != set(zone_ids):
            missing = set(zone_ids) - set(polygons)
            raise ValueError(
                "6区画のカメラ座標がそろっていません。未登録: " +
                ", ".join(sorted(missing))
            )
    elif set(polygons) == set(expected) and len(zone_ids) < 6:
        print("【復元可能】区画ID一覧は不足していますが、画像上の6区画座標が保存されています。")
        print("【確認必須】space_001～006として復元します。実映像の重ね合わせで確認してください。")
        zone_ids = expected
    else:
        raise ValueError(
            f"移行元に6区画分のカメラ座標がありません"
            f"（区画ID {len(zone_ids)}件、座標 {len(polygons)}件）。"
            "ノートPCで実際に6区画を登録したconfig.jsonをコピーしてください"
        )
    repaired = {}
    for uid in zone_ids:
        try:
            repaired[uid] = normalize_corners(polygons[uid])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{uid} の四隅を確認してください: {exc}") from exc
    return zone_ids, repaired


def candidate_config_files(directory, active_config):
    """Find local JSON backups only; never read or transmit private files."""
    directory = Path(directory)
    active = Path(active_config).resolve()
    candidates = []
    for pattern in (
        "config_backup*.json",
        "config_from_laptop*.json",
        "config_laptop*.json",
        "config_notebook*.json",
        "config_old*.json",
    ):
        candidates.extend(directory.glob(pattern))
    unique = {p.resolve() for p in candidates if p.is_file()
              and p.resolve() != active}
    return sorted(unique, key=lambda p: p.stat().st_mtime, reverse=True)


def select_source_path(desktop_path, explicit_path=None, input_fn=input):
    """Show inventory before selecting. Incomplete default backups are skipped."""
    desktop_path = Path(desktop_path).resolve()
    if explicit_path is not None:
        source = Path(explicit_path).expanduser().resolve()
        if source == desktop_path or not source.is_file():
            raise ValueError("指定したバックアップが存在しないか、現在のconfig.json自身です")
        return source

    choices = candidate_config_files(desktop_path.parent, desktop_path)
    readable = []
    print("========== 区画バックアップの検索結果 ==========")
    for filename in choices:
        try:
            info = zone_inventory(read_settings(filename))
        except (OSError, json.JSONDecodeError, UnicodeError, ValueError):
            info = {"ids": 0, "polygons": 0, "valid_polygons": 0, "complete": False}
        readable.append((filename, info))
        state = "利用可能" if info["complete"] else "不完全"
        print(f"【{len(readable)}】{filename.name} / "
              f"区画ID {info['ids']} / カメラ座標 {info['valid_polygons']} / {state}")
    valid = [p for p, info in readable if info["complete"]]
    if len(valid) == 1:
        print(f"【自動選択】6区画のある {valid[0].name} を使用します。")
        return valid[0]
    if len(valid) > 1:
        print("【複数候補】元のカメラに対応するファイル番号を選んでください。")
        selection = input_fn("使用するファイルの番号（キャンセルはEnter）: ").strip()
        if not selection.isdecimal():
            raise ValueError("バックアップを選択しなかったため変更していません")
        index = int(selection) - 1
        if index < 0 or index >= len(readable) or not readable[index][1]["complete"]:
            raise ValueError("選択したファイルに6区画がないため変更していません")
        return readable[index][0]

    print("【6区画のバックアップがありません】現行のデスクトップ設定は変更しません。")
    print("ノートPCの parking-guide-admin\\parking-vision\\config.json を")
    print("USB等でこのフォルダに config_from_laptop.json の名前でコピーしてください。")
    print("すでにコピー済みなら、そのファイルのフルパスも指定できます。")
    raw = input_fn("移行元のファイルパス（まだ無ければEnterで中止）: ").strip().strip('"')
    if not raw:
        raise ValueError("6区画の登録データがないため変更していません")
    other = Path(raw).expanduser().resolve()
    if not other.is_file() or other == desktop_path:
        raise ValueError("指定した元ファイルが見つからないか、現在の設定と同じです")
    return other


def transfer_settings(old_settings, desktop_settings, frame_width, frame_height):
    """Prepare a safe result; no file is written before camera confirmation."""
    if desktop_settings.get("facility_id") != EXPECTED_FACILITY:
        raise ValueError("移行先が自宅駐車場の設定ではありません")
    if desktop_settings.get("camera_verified_external") is not True:
        raise ValueError("先にデスクトップで外付けカメラを目視確認してください")
    camera_number = desktop_settings.get("source")
    if not isinstance(camera_number, int) or camera_number < 0:
        raise ValueError("デスクトップのカメラ番号を先に設定してください")
    if min(frame_width, frame_height) <= 0:
        raise ValueError("デスクトップのカメラ映像が取得できていません")

    zone_ids, zones = source_zones(old_settings)
    old_kind = str(old_settings.get("camera_kind", "usb")).lower()
    desktop_kind = str(desktop_settings.get("camera_kind", "usb")).lower()
    if old_kind != desktop_kind:
        raise ValueError(
            "CamoとUSBカメラの座標は流用できません。同じカメラ種類で確認してください"
        )
    previous = old_settings.get("calibration_capture") or {}
    old_width = int(previous.get("width") or 0)
    old_height = int(previous.get("height") or 0)
    if old_width > 0 and old_height > 0:
        delta = abs(old_width / old_height - frame_width / frame_height)
        if delta > .025:
            raise ValueError(
                f"以前の映像は{old_width}x{old_height}、現在は{frame_width}x{frame_height}です。"
                "縦横比が異なるため、枠の再登録が必要です"
            )

    result = deepcopy(desktop_settings)
    result["space_uids"] = zone_ids
    result["space_zones"] = zones
    for name in ("entry_zone", "exit_zone"):
        points = old_settings.get(name) or []
        if points:
            if len(points) != 4:
                raise ValueError(f"{name} は四隅の登録状態を確認してください")
            result[name] = normalize_corners(points)
        else:
            result[name] = []
    # Do not reuse camera number or metadata from notebook.
    result["calibration_capture"] = {
        "width": int(frame_width),
        "height": int(frame_height),
        "source": str(camera_number),
        "kind": desktop_kind,
    }
    # A human's prior empty-space approval is never safe to carry to another
    # computer or to a later test session.
    result["initially_confirmed_empty_uids"] = []
    result.pop("initial_empty_verified_at", None)
    result.pop("initial_empty_valid_seconds", None)
    result["allow_unverified_initial_empty"] = False
    # Preserve desktop's model paths, credentials, backend, camera ID, etc.
    assert_calibrated_view(result, frame_width, frame_height)
    return result


def _draw_overlay(frame, settings):
    import cv2

    view = frame.copy()
    height, width = view.shape[:2]
    for number, uid in enumerate(settings["space_uids"], start=1):
        polygon = settings["space_zones"][uid]
        points = [(round(x * width), round(y * height)) for x, y in polygon]
        for a, b in zip(points, points[1:] + points[:1]):
            cv2.line(view, a, b, (50, 225, 255), 4, cv2.LINE_AA)
            cv2.line(view, a, b, (0, 0, 0), 1, cv2.LINE_AA)
        x, y = points[0]
        text = f"{number} / {uid}"
        pos = (max(8, min(width - 190, x + 7)), max(25, min(height - 8, y + 28)))
        cv2.putText(view, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    .72, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(view, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    .72, (40, 255, 225), 2, cv2.LINE_AA)
    return view


def _make_panel():
    """Readably separate Japanese controls from the camera view."""
    import cv2
    import numpy as np
    from select_external_camera import PREVIEW_HEIGHT, PREVIEW_WIDTH

    panel = np.full((PREVIEW_HEIGHT, PREVIEW_WIDTH, 3), (23, 26, 29), dtype=np.uint8)
    try:
        from PIL import Image, ImageDraw, ImageFont

        fonts = (Path(r"C:\Windows\Fonts\meiryo.ttc"),
                 Path(r"C:\Windows\Fonts\YuGothM.ttc"),
                 Path(r"C:\Windows\Fonts\msgothic.ttc"))
        found = next((p for p in fonts if p.is_file()), None)
        if found is None:
            raise OSError("日本語フォントなし")
        title = ImageFont.truetype(str(found), 29)
        detail = ImageFont.truetype(str(found), 22)
        rgb = Image.fromarray(cv2.cvtColor(panel, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(rgb)
        d.text((22, 14), "ノートPCの6区画と、現在のカメラ映像を照合",
               font=title, fill=(255, 255, 255))
        d.text((22, 66), "黄色い線が実際の駐車枠の四隅に一致するか確認",
               font=detail, fill=(180, 222, 250))
        d.text((22, 614), "[ S ] 全6区画が一致　　[ Q ] 中止（変更なし）",
               font=title, fill=(255, 255, 255))
        d.text((22, 680), "一致しなければ保存せず、カメラ位置か区画を再調整します",
               font=detail, fill=(200, 205, 215))
        return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    except (ImportError, OSError):
        for text, y, scale in (
            ("COMPARE ALL SIX PARKING ZONES", 43, .9),
            ("Yellow polygons MUST match the actual parking spaces.", 84, .62),
            ("S = ALL SIX MATCH    Q = CANCEL WITHOUT SAVING", 649, .70),
            ("If mismatched, recalibrate the camera or parking polygons.", 694, .60),
        ):
            cv2.putText(panel, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (245, 245, 245), 2, cv2.LINE_AA)
        return panel


def camera_alignment_preview(camera, settings):
    import cv2
    from select_external_camera import (
        PREVIEW_HEIGHT, PREVIEW_WIDTH, render_preview_frame,
    )

    window = "Parking zone transfer - S=all correct / Q=cancel"
    panel = _make_panel()
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, PREVIEW_WIDTH, PREVIEW_HEIGHT)
    try:
        while True:
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError("カメラ映像を取得できません。設定は変更していません")
            marked = _draw_overlay(frame, settings)
            cv2.imshow(window, render_preview_frame(marked, panel))
            key = cv2.waitKey(25) & 0xFF
            if key in (ord("s"), ord("S")):
                return True
            if key in (ord("q"), ord("Q"), 27):
                return False
    finally:
        cv2.destroyWindow(window)


def main():
    parser = argparse.ArgumentParser(
        description="旧PCの駐車6区画をデスクトップのカメラ映像で照合し、安全に取り込む")
    parser.add_argument("--config", default="config.json", help="デスクトップ側の現行設定")
    parser.add_argument("--from-config", dest="from_config", default=None,
                        help="ノートPC設定または区画が残っているバックアップJSON")
    args = parser.parse_args()
    desktop_path = Path(args.config).resolve()
    if not desktop_path.is_file():
        raise SystemExit("デスクトップのconfig.jsonがありません")
    try:
        source_path = select_source_path(desktop_path, args.from_config)
    except ValueError as exc:
        raise SystemExit(f"【移行中止】{exc}") from exc

    old_settings = read_settings(source_path)
    desktop_settings = read_settings(desktop_path)
    try:
        source_ids, zones = source_zones(old_settings)
    except ValueError as exc:
        raise SystemExit(f"【移行中止】{exc}") from exc
    print("========== 旧PCの駐車区画を引き継ぐ ==========")
    print(f"【移行元】{source_path.name}")
    print(f"【区画】{', '.join(source_ids)}")
    for warning in audit_zones(zones):
        print(f"【要確認】{warning}")
    if desktop_settings.get("camera_verified_external") is not True:
        raise SystemExit("【未確認】まず新しいPCで外付けUSBカメラを目視確認してください")

    import cv2
    from camera_recording import open_camera

    w, h, fps = capture_preferences(desktop_settings)
    camera = open_camera(cv2, desktop_settings["source"],
                         desktop_settings.get("camera_backend", "auto"),
                         desktop_settings.get("camera_manual_exposure"),
                         w, h, fps)
    try:
        if not camera.isOpened():
            raise SystemExit("【中止】デスクトップの外付けカメラを開けません")
        ok, frame = camera.read()
        if not ok or frame is None:
            raise SystemExit("【中止】カメラから映像を取得できません")
        try:
            candidate = transfer_settings(old_settings, desktop_settings,
                                          frame.shape[1], frame.shape[0])
        except ValueError as exc:
            raise SystemExit(f"【移行中止】{exc}") from exc
        print("【重要】黄色の区画線が実際の全6区画と一致するか、必ず確認してください。")
        print("一致すれば映像画面でS / ずれていたらQで中止（設定は変わりません）。")
        approved = camera_alignment_preview(camera, candidate)
    finally:
        camera.release()
        cv2.destroyAllWindows()
    if not approved:
        print("【変更なし】区画の位置が一致しないため移行していません")
        return

    answer = input("実際の6区画と線が一致した場合のみ「一致」と入力: ").strip()
    if answer != "一致":
        print("【変更なし】明示確認がないため保存していません")
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = desktop_path.with_name("config_backup_before_zone_transfer_" + timestamp + ".json")
    shutil.copy2(desktop_path, backup)
    desktop_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print("【移行完了】6区画の座標をデスクトップへ反映しました")
    print(f"【バックアップ】{backup}")
    print(f"【現在のカメラ番号】{candidate['source']}（ノートPCの番号を流用していません）")
    print("【次の操作】start.ps1 -Mode camera を使ってクラウド送信なしで確認してください")


if __name__ == "__main__":
    main()
