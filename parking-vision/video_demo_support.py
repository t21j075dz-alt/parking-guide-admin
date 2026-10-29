#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""録画実演と通常の実カメラ運用を分離する安全装置。"""
from __future__ import annotations

from urllib import parse, request

VIDEO_FACILITY = "home-video-demo-001"
SOURCE = "recorded_video_demo"


def require_demo_mode(config, args):
    """A replay can never claim to be a current camera at home-test-001."""
    video = bool(args.video)
    if args.demo_publish and not video:
        raise ValueError("録画デモの共有には --video が必要です")
    if video:
        if config.get("facility_id") != VIDEO_FACILITY:
            raise ValueError(
                "動画の実演には専用のconfig_video_demo.jsonを使用してください。"
                "実際の自宅駐車場には録画の状態を送信できません"
            )
        if config.get("allow_unverified_initial_empty"):
            raise ValueError("録画実演では根拠のない空き初期設定は使用できません")
    elif config.get("facility_id") == VIDEO_FACILITY:
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
    window = "VIDEO DEMO - verify six zones (S=OK Q=cancel)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1180, 780)
    print("【目視確認】これは録画動画です。黄色・灰色の区画が実際の枠位置と一致していますか？")
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


def draw_demo_phase_labels(view, cv2, zones, phases):
    """Show intuitive Japanese labels in recorded-demo frames.

    OpenCV's default font cannot draw Japanese. Windows fonts + Pillow
    are preferred; a readable English fallback remains for other OSes.
    """
    from pathlib import Path
    import numpy as np

    from recorded_parking_states import DISPLAY_PHASES
    view = view.copy()
    height, width = view.shape[:2]
    placements = []
    for uid, polygon in zones.items():
        phase = (phases or {}).get(uid, "unknown")
        x, y = polygon[0]
        px = max(8, min(width - 265, int(width * x)))
        py = max(46, min(height - 33, int(height * y) + 49))
        placements.append((uid, phase, px, py))
    try:
        from PIL import Image, ImageDraw, ImageFont

        fonts = [Path(r"C:\Windows\Fonts\meiryo.ttc"),
                 Path(r"C:\Windows\Fonts\YuGothM.ttc"),
                 Path(r"C:\Windows\Fonts\msgothic.ttc")]
        font_path = next((p for p in fonts if p.is_file()), None)
        if font_path is None:
            raise OSError("Japanese font unavailable")
        font = ImageFont.truetype(str(font_path), 21)
        canvas = Image.fromarray(cv2.cvtColor(view, cv2.COLOR_BGR2RGB))
        painter = ImageDraw.Draw(canvas)
        for uid, phase, px, py in placements:
            label = f"{uid}: {DISPLAY_PHASES.get(phase, '確認中')}"
            area = painter.textbbox((px+5, py+2), label, font=font)
            painter.rectangle((px, py, min(width-1, area[2]+9),
                               min(height-1, area[3]+6)), fill=(22, 30, 42))
            painter.text((px+5, py+2), label, font=font, fill=(255, 255, 255))
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
    except (ImportError, OSError, ValueError):
        english = {
            "available": "FREE", "parking_in": "PARKING IN",
            "stopped": "STOPPED", "exiting": "EXITING", "unknown": "CHECKING"
        }
        for uid, phase, px, py in placements:
            label = f"{uid}: {english.get(phase, 'CHECKING')}"
            cv2.rectangle(view, (px, py-24), (min(width-1, px+260), py+8),
                          (22, 30, 42), -1)
            cv2.putText(view, label, (px+5, py), cv2.FONT_HERSHEY_SIMPLEX,
                        .57, (255, 255, 255), 2, cv2.LINE_AA)
        return view


def demo_status_rows(config, statuses, timestamp, phases=None):
    """Restrict writes to video demo; keep four-status API plus per-slot phase."""
    from recorded_parking_states import VALID_PHASES, STATUS_FOR_PHASE

    if config.get("facility_id") != VIDEO_FACILITY:
        raise ValueError("実カメラ施設に録画の判定結果は送信できません")
    phases = phases or {}
    result = []
    for uid, status in statuses.items():
        phase = phases.get(uid, "unknown")
        if phase not in VALID_PHASES or status != STATUS_FOR_PHASE[phase]:
            raise ValueError(f"{uid} の段階と空き状態が一致していません")
        result.append({
            "facility_id": VIDEO_FACILITY,
            "space_uid": uid, "status": status,
            "occupancy_phase": phase,
            "confidence": None, "source": SOURCE,
            "checked_at": timestamp,
        })
    return result


def set_demo_visibility(writer, published):
    """Toggle only video-demo visibility, with the signed-in user's JWT.

    A database row must already exist; RLS denies writes outside membership.
    Do not expose service_role or bypass RLS.
    """
    writer._ensure_token()
    address = (
        f"{writer.url}/rest/v1/parking_live_visibility?"
        f"facility_id=eq.{parse.quote(VIDEO_FACILITY)}"
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
    if len(rows) != 1 or rows[0].get("facility_id") != VIDEO_FACILITY:
        raise ValueError(
            "録画実演の公開設定を変更できません。専用施設のDB初期設定または権限を確認してください"
        )
    print("【録画実演の共有】" + ("ON（実カメラではありません）" if published else "OFF"))
