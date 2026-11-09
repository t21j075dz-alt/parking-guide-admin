#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""録画実演と通常の実カメラ運用を分離する安全装置。"""
from __future__ import annotations

from urllib import parse, request

VIDEO_FACILITY = "home-video-demo-001"
NIKKO_VIDEO_FACILITY = "nikko-test-001"
VIDEO_FACILITIES = frozenset((VIDEO_FACILITY, NIKKO_VIDEO_FACILITY))
SOURCE = "recorded_video_demo"


def checked_demo_facility(config):
    """録画結果の共有先は自宅録画専用または日光録画専用に限定。"""
    facility = config.get("facility_id")
    if facility == VIDEO_FACILITY:
        return facility
    if facility == NIKKO_VIDEO_FACILITY:
        from nikko_video_config import checked_config
        checked_config(config)
        return facility
    raise ValueError("録画判定は録画専用施設にのみ送信できます。実カメラ・通常施設へは送信できません")


def require_demo_mode(config, args):
    """録画と実カメラを厳密に分ける。日光は校正した動画以外を拒否。"""
    video = bool(args.video)
    if args.demo_publish and not video:
        raise ValueError("録画デモの共有には --video が必要です")
    if video:
        checked_demo_facility(config)
        if config.get("allow_unverified_initial_empty"):
            raise ValueError("録画実演では根拠のない空き初期設定は使用できません")
        if config["facility_id"] == NIKKO_VIDEO_FACILITY:
            from nikko_video_config import checked_ready
            checked_ready(config, args.video)
    elif config.get("facility_id") in VIDEO_FACILITIES:
        raise ValueError("録画実演専用の設定は実カメラで使用できません")


def parse_verified_empty(value, zones):
    """Explicit operator-confirmed empty spaces at the first recorded frame."""
    result = [x.strip() for x in (value or "").split(",") if x.strip()]
    if len(result) != len(set(result)) or any(x not in zones for x in result):
        raise ValueError("空きと確認した区画のIDが不正です。カンマ区切りで登録済みIDを入力してください")
    return result


def draw_demo_watermark(view, cv2, elapsed):
    """Persistent disclaimer on annotated output, including recorded MP4."""
    view = view.copy()
    text = f"RECORDED VIDEO DEMO / NOT LIVE / {elapsed:.1f}s"
    cv2.rectangle(view, (0, 0), (min(view.shape[1], 940), 46), (5, 20, 98), -1)
    cv2.putText(view, text, (12, 32), cv2.FONT_HERSHEY_SIMPLEX,
                .68, (255, 255, 255), 2, cv2.LINE_AA)
    return view


def verify_overlay_with_operator(frame, zones, cv2):
    """Never start a demo publish before a visual check of the video itself."""
    from monitor import overlay

    view = overlay(frame, zones,
                   {uid: "unknown" for uid in zones}, [], [])
    view = draw_demo_watermark(view, cv2, 0)
    window = f"RECORDED VIDEO - check {len(zones)} zones (S=OK Q=cancel)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1180, 780)
    print("【目視確認】これは過去の録画です。"+str(len(zones))+"区画の線が映像と一致しているか確認してください。")
    print("映像のウィンドウで S=一致 / Q=中止。ずれているときはSを押さないでください。")
    try:
        while True:
            cv2.imshow(window, view)
            key = cv2.waitKey(50) & 0xFF
            if key in (ord("s"), ord("S")):
                return True
            if key in (ord("q"), ord("Q"), 27):
                return False
    finally:
        cv2.destroyWindow(window)


def demo_badge_grid(width, count):
    """Compute a non-overlapping grid reserved BELOW the actual camera frame.

    In the previous recording, six labels were drawn over the vehicles and
    each other. They now live in a separate strip, with a maximum of six
    short labels per row. This is display-only; no geometry or status changes.
    """
    if width < 180 or count < 0:
        raise ValueError("映像の横幅または区画数が不正です")
    columns = max(1, min(6, width // 185))
    rows = (count + columns - 1) // columns
    return columns, rows, width // columns


def draw_demo_phase_labels(view, cv2, zones, phases):
    """Show recorded-video space phases in a separate, legible footer.

    Never cover the camera view with black Japanese status rectangles. Actual
    status computation, timestamp, video timing and images stay unchanged.
    """
    from pathlib import Path
    from recorded_parking_states import DISPLAY_PHASES

    height, width = view.shape[:2]
    phases = phases or {}
    if len(zones) > 12:
        from collections import Counter
        counts = Counter(phases.values())
        view = cv2.copyMakeBorder(view, 0, 34, 0, 0,
                                  cv2.BORDER_CONSTANT, value=(22, 25, 29))
        occupied = sum(counts.get(p, 0) for p in ("parking_in", "stopped", "exiting"))
        line = (f"RECORDED SPACES {len(zones)} | FREE {counts.get('available', 0)}"
                f" | OCCUPIED {occupied} | CHECKING {counts.get('unknown', 0)}")
        cv2.putText(view, line, (12, view.shape[0]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, .53, (255, 255, 255), 1, cv2.LINE_AA)
        return view

    columns, rows, cell_width = demo_badge_grid(width, len(zones))
    line_height = 44
    # Existing text diagnostics already live in a 98px footer; append our own
    # strip so they are not covered either.
    footer = cv2.copyMakeBorder(
        view, 0, max(1, rows) * line_height + 8, 0, 0,
        cv2.BORDER_CONSTANT, value=(22, 25, 29)
    )
    from recorded_parking_states import VALID_PHASES
    colors = {
        "available": (65, 116, 58),
        "parking_in": (32, 85, 135),
        "stopped": (25, 93, 137),
        "exiting": (42, 105, 132),
        "unknown": (75, 75, 75),
    }
    badges = []
    for index, (uid, _) in enumerate(zones.items()):
        phase = phases.get(uid, "unknown")
        if phase not in VALID_PHASES:
            phase = "unknown"
        column, row = index % columns, index // columns
        x1 = column * cell_width + 4
        x2 = min(width - 4, (column + 1) * cell_width - 4)
        y1 = height + row * line_height + 5
        y2 = y1 + 35
        cv2.rectangle(footer, (x1, y1), (x2, y2), colors[phase], -1)
        cv2.rectangle(footer, (x1, y1), (x2, y2),
                      (160, 170, 175), 1)
        number = str(uid).removeprefix("space_").lstrip("0") or "0"
        badges.append((uid, phase, number, x1, y1))

    # Display Japanese where an installed Windows font is available.
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
        fonts = [Path(r"C:\Windows\Fonts\meiryo.ttc"),
                 Path(r"C:\Windows\Fonts\YuGothM.ttc"),
                 Path(r"C:\Windows\Fonts\msgothic.ttc")]
        font_path = next((p for p in fonts if p.is_file()), None)
        if font_path is None:
            raise OSError("Japanese font unavailable")
        font = ImageFont.truetype(str(font_path), 19)
        picture = Image.fromarray(cv2.cvtColor(footer, cv2.COLOR_BGR2RGB))
        painter = ImageDraw.Draw(picture)
        for uid, phase, number, x1, y1 in badges:
            label = f"{number}番：{DISPLAY_PHASES.get(phase, '確認中')}"
            painter.text((x1 + 9, y1 + 4), label, font=font, fill=(255, 255, 255))
        return cv2.cvtColor(np.asarray(picture), cv2.COLOR_RGB2BGR)
    except (ImportError, OSError, ValueError):
        english = {
            "available": "FREE", "parking_in": "PARKING",
            "stopped": "STOPPED", "exiting": "EXITING", "unknown": "CHECK"
        }
        for uid, phase, number, x1, y1 in badges:
            cv2.putText(
                footer, f"{number}: {english.get(phase, 'CHECK')}",
                (x1+8, y1+25), cv2.FONT_HERSHEY_SIMPLEX, .53,
                (255, 255, 255), 1, cv2.LINE_AA,
            )
        return footer


def demo_status_rows(config, statuses, timestamp, phases=None):
    """Restrict writes to video demo; keep four-status API plus per-slot phase."""
    from recorded_parking_states import VALID_PHASES, STATUS_FOR_PHASE

    facility = checked_demo_facility(config)
    phases = phases or {}
    result = []
    for uid, status in statuses.items():
        phase = phases.get(uid, "unknown")
        if phase not in VALID_PHASES or status != STATUS_FOR_PHASE[phase]:
            raise ValueError(f"{uid} の段階と空き状態が一致していません")
        result.append({
            "facility_id": facility,
            "space_uid": uid, "status": status,
            "occupancy_phase": phase,
            "confidence": None, "source": SOURCE,
            "checked_at": timestamp,
        })
    return result


def set_demo_visibility(writer, published, facility_id=VIDEO_FACILITY):
    """Toggle only video-demo visibility, with the signed-in user's JWT.

    A database row must already exist; RLS denies writes outside membership.
    Do not expose service_role or bypass RLS.
    """
    if facility_id not in VIDEO_FACILITIES:
        raise ValueError("録画デモ以外の公開設定は変更できません")
    writer._ensure_token()
    address = (
        f"{writer.url}/rest/v1/parking_live_visibility?"
        f"facility_id=eq.{parse.quote(facility_id)}"
    )
    body = b'{"is_published":true}' if published else b'{"is_published":false}'
    req = request.Request(address, data=body, method="PATCH", headers={
        "apikey": writer.key,
        "Authorization": f"Bearer {writer.access_token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    })
    import json
    with request.urlopen(req, timeout=10) as response:
        rows = json.loads(response.read() or b"[]")
    if len(rows) != 1 or rows[0].get("facility_id") != facility_id:
        raise ValueError(
            "録画実演の公開設定を変更できません。専用施設のDB初期設定または権限を確認してください"
        )
    print("【録画実演の共有】" + ("ON（実カメラではありません）" if published else "OFF"))


def invalidate_nikko_outside_camera_rows(writer, monitored_uids):
    """前の録画だけに映っていた区画を期限切れにしてから共有する。

    既存の公開状態をOFFにした後、現在のカメラにない区画の行だけ
    明示的にUNKNOWN・過去日時へ。これで短時間の録画切替でも
    古い「空き」が新しい録画の監視対象として再表示されない。
    """
    import json
    from nikko_video_config import UID_PATTERN
    monitored = set(monitored_uids)
    if (not monitored or
            len(monitored) != len(list(monitored_uids)) or
            not all(isinstance(uid, str) and UID_PATTERN.fullmatch(uid) for uid in monitored)):
        raise ValueError("録画の監視区画IDが不正です。クラウド共有しません")
    writer._ensure_token()
    address=(f"{writer.url}/rest/v1/parking_live_status?"
             f"facility_id=eq.{NIKKO_VIDEO_FACILITY}&select=space_uid&limit=10000")
    req=request.Request(address,method="GET",headers={
        "apikey":writer.key,
        "Authorization":f"Bearer {writer.access_token}",
    })
    with request.urlopen(req,timeout=10) as response:
        rows=json.loads(response.read() or b"[]")
    if not isinstance(rows,list) or len(rows)>9999:
        raise ValueError("以前の録画区画を安全に取得できません。共有しません")
    others={row.get("space_uid") for row in rows
            if isinstance(row,dict) and isinstance(row.get("space_uid"),str)}-monitored
    if not all(UID_PATTERN.fullmatch(uid) for uid in others):
        raise ValueError("以前の区画IDが不正です。録画共有しません")
    if others:
        writer.upsert("parking_live_status",[
            {"facility_id":NIKKO_VIDEO_FACILITY,"space_uid":uid,
             "status":"unknown","occupancy_phase":"unknown",
             "source":SOURCE,"confidence":None,
             "checked_at":"2000-01-01T00:00:00+00:00"}
            for uid in sorted(others)],"facility_id,space_uid")
    print(f"【録画切替】以前の画角だけにあった{len(others)}区画を未確認に更新しました。")
    return len(others)
