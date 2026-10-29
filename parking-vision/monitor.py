#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""駐車場カメラ → YOLO → 車両追跡 → Supabase。

使い方: python monitor.py --config config.json --preview
※ カメラ映像はノートPC内に分割録画します。クラウドには状態と匿名追跡情報のみ送ります。
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from getpass import getpass
import json
import os
from pathlib import Path
import sys
import time
from urllib import error, parse, request
from uuid import uuid4

from camera_recording import RecordingCamera, open_camera
from camera_profiles import capture_preferences, assert_calibrated_view, fit_preview_dimensions
from yolo_visual_recording import YoloVisualRecorder
from camera_snapshots import SnapshotPublisher
from stable_ids import StableIdMatcher
from wheel_geometry import estimate_wheel_contacts
from vehicle_zone import annotate_vehicle_zones

# 古いconfig.jsonでも、同梱の駐車場用トラッカーを優先する。
_TRACKER_PROFILE = Path(__file__).with_name("botsort-parking.yaml")
DEFAULT_TRACKER = str(_TRACKER_PROFILE) if _TRACKER_PROFILE.is_file() else "botsort.yaml"

# VisDroneのクラス名と標準COCOのクラス名を両方扱う。
# ユーザーが以前学習したVisDroneモデルは、motor=二輪車、
# pedestrian/people=歩行者などの名前を使っている。
VEHICLE_NAMES = {
    "car", "truck", "bus", "motorcycle", "bicycle", "vehicle", "van",
    "tricycle", "awning_tricycle",
}
CLASS_ALIASES = {
    "pedestrian": "person",
    "people": "person",
    "motor": "motorcycle",
}
BLOCKING_NAMES = {
    "person", "cone", "traffic_cone", "traffic cone", "カラーコーン",
    "shopping_cart", "shopping cart", "cart", "trolley", "カート",
    "barrier", "barricade", "bollard", "obstacle", "障害物",
}
STATUS_NAMES = {"available": "空き", "occupied": "駐車中", "blocked": "障害物あり", "unknown": "確認できない"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def inside(point, polygon) -> bool:
    """正規化した画面座標(0～1)が四角形/多角形に含まれるか調べる。"""
    x, y = point
    hit = False
    for index, (a, b) in enumerate(polygon):
        c, d = polygon[(index + 1) % len(polygon)]
        if (b > y) != (d > y) and x < (c - a) * (y - b) / (d - b) + a:
            hit = not hit
    return hit


def valid_polygon(points) -> bool:
    return isinstance(points, list) and len(points) >= 3 and all(
        isinstance(p, list) and len(p) == 2
        and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in p)
        for p in points
    )


def load_config(path: str) -> dict:
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("facility_id", "camera_id", "supabase_url", "publishable_key"):
        if not content.get(key):
            raise ValueError(f"設定ファイルの {key} を入力してください")
    # USBカメラ番号0は有効。Pythonでは bool(0) == False なので別判定する。
    if content.get("source") is None or content.get("source") == "":
        raise ValueError("カメラの source を入力してください")
    # 自宅実験は、目視確認した外付けUSBまたはCamo仮想カメラのみを許可。
    # Camoの設定はUSBカメラとは別JSONにして、区画座標を混ぜない。
    if content.get("facility_id") == "home-test-001":
        if (not isinstance(content["source"], int) or content["source"] < 0
                or content.get("camera_verified_external") is not True):
            raise ValueError(
                "外付けUSB WebカメラまたはCamoの選択・目視確認が必要です。Camoならsetup_camo.pyを実行してください"
            )
    zones = content.get("space_zones") or {}
    if not zones:
        raise ValueError("駐車枠の撮影範囲が未登録です。先に calibrate.py を実行してください")
    for uid, polygon in zones.items():
        if not valid_polygon(polygon):
            raise ValueError(f"{uid} の四隅座標が正しくありません")
    for name in ("entry_zone", "exit_zone"):
        if content.get(name) and not valid_polygon(content[name]):
            raise ValueError(f"{name} の範囲が正しくありません")
    confirmed = content.get("initially_confirmed_empty_uids", [])
    if not isinstance(confirmed, list) or any(uid not in zones for uid in confirmed):
        raise ValueError("initially_confirmed_empty_uids は登録済み区画IDにしてください")
    for key in ("confidence", "tracking_confidence"):
        value = float(content.get(key, .35 if key == "confidence" else .15))
        if not 0 < value <= 1:
            raise ValueError(f"{key} は0より大きく1以下で設定してください")
    if float(content.get("occupied_hold_seconds", 8)) < 0:
        raise ValueError("occupied_hold_seconds は0以上にしてください")
    if float(content.get("reid_window_seconds", 12)) <= 0:
        raise ValueError("reid_window_seconds は0より大きくしてください")
    return content


def space_for(point, zones) -> str | None:
    matches = [uid for uid, polygon in zones.items() if inside(point, polygon)]
    return matches[0] if len(matches) == 1 else None  # 重なる場合は特定できない


@dataclass
class Vehicle:
    camera_id: str
    facility_id: str
    track_id: int
    session_id: str = field(default_factory=lambda: str(uuid4()))
    phase: str = "entering"
    arrived_from_outside: bool = False
    entered_at: str = field(default_factory=utc_now)
    parked_at: str | None = None
    left_space_at: str | None = None
    exited_at: str | None = None
    last_seen_at: str = field(default_factory=utc_now)
    seen_monotonic: float = 0.0
    position_x: float = 0.0
    position_y: float = 0.0
    space_uid: str | None = None
    candidate_uid: str | None = None
    candidate_since: float = 0.0
    candidate_started_at: str | None = None
    outside_since: float = 0.0
    outside_started_at: str | None = None
    locations: deque = field(default_factory=lambda: deque(maxlen=90))

    def observe(self, point: tuple[float, float], uid: str | None,
                in_exit: bool, now: float, park_seconds: float):
        self.seen_monotonic = now
        self.last_seen_at = utc_now()
        self.position_x, self.position_y = point
        self.locations.append((now, point))
        if uid is None and self.phase in {"entering", "moving"}:
            self.arrived_from_outside = True
        recent = [p for t, p in self.locations if now - t <= 3]
        stationary = len(recent) >= 3 and max(
            ((p[0] - recent[0][0]) ** 2 + (p[1] - recent[0][1]) ** 2) ** 0.5
            for p in recent
        ) < 0.015

        if self.phase in {"entering", "moving"}:
            if uid and stationary:
                if self.candidate_uid != uid:
                    self.candidate_uid, self.candidate_since = uid, now
                    self.candidate_started_at = utc_now()
                elif now - self.candidate_since >= park_seconds:
                    self.phase, self.space_uid = "parked", uid
                    # 駐車開始は「確定した時刻」ではなく「停止を始めた時刻」。
                    # 動画開始時点で既に駐車していた車は、駐車開始時刻が不明。
                    # 入場/移動を画面で確認した車だけ開始時刻を確定する。
                    self.parked_at = (self.candidate_started_at or utc_now()) if self.arrived_from_outside else None
            else:
                self.candidate_uid = None
                self.candidate_started_at = None
                if self.phase == "entering" and len(self.locations) > 3:
                    self.phase = "moving"

        if self.phase == "parked":
            if uid != self.space_uid:
                if self.outside_since == 0.0:
                    self.outside_since = now
                    self.outside_started_at = utc_now()
                elif now - self.outside_since >= 2:
                    self.phase = "exiting"
                    self.left_space_at = self.outside_started_at or utc_now()
            else:
                self.outside_since = 0.0
                self.outside_started_at = None

        if in_exit and self.phase in {"moving", "exiting"}:
            self.phase = "exited"
            self.exited_at = utc_now()

    def row(self) -> dict:
        return {
            "session_id": self.session_id, "facility_id": self.facility_id,
            "camera_id": self.camera_id, "track_id": self.track_id,
            "phase": self.phase, "space_uid": self.space_uid,
            "entered_at": self.entered_at, "parked_at": self.parked_at,
            "left_space_at": self.left_space_at, "exited_at": self.exited_at,
            "last_seen_at": self.last_seen_at,
            "position_x": self.position_x, "position_y": self.position_y,
        }


class VehicleTracker:
    def __init__(self, facility_id: str, camera_id: str, park_seconds: float = 5,
                 lost_seconds: float = 12):
        self.facility_id, self.camera_id = facility_id, camera_id
        self.park_seconds = park_seconds
        self.lost_seconds = lost_seconds
        self.vehicles: dict[int, Vehicle] = {}

    def update(self, detections: list[dict], zones: dict, exit_zone: list,
               now: float) -> list[dict]:
        changed = []
        for detected in detections:
            track_id = detected.get("track_id")
            if track_id is None:
                continue  # YOLO追跡IDなしでも区画の占有判定は別処理で行う
            point = detected["point"]
            uid = detected.get("zone_candidate") if "zone_candidate" in detected else space_for(point, zones)
            entry = self.vehicles.get(int(track_id))
            is_new = entry is None
            if is_new:
                entry = Vehicle(self.camera_id, self.facility_id, int(track_id))
                self.vehicles[int(track_id)] = entry
            previous = entry.phase
            entry.observe(point, uid, bool(exit_zone and inside(point, exit_zone)), now, self.park_seconds)
            if is_new or entry.phase != previous:
                changed.append(entry.row())
        for track_id, entry in list(self.vehicles.items()):
            if entry.phase == "exited":
                changed.append(entry.row())
                del self.vehicles[track_id]
            elif now - entry.seen_monotonic > self.lost_seconds:
                entry.phase = "lost"  # IDが消えたことを「退出」とは決めつけない
                changed.append(entry.row())
                del self.vehicles[track_id]
        return changed


class SpaceObserver:
    """誤った「空き」を防ぐため不確実な区画をunknownに戻す。

    車両が一時的に検出されなくなっても「空き」にしない。過去に
    占有された区画は、追跡上の出庫を確認した場合のみ「空き」に戻す。
    初期時点で車のない区画も、明示設定がなければunknownのまま。
    """

    def __init__(self, space_uids, allow_initial_empty=False,
                 absence_hold_seconds=8.0, initially_confirmed_empty_uids=(),
                 blocked_confirm_seconds=2.0):
        self.states = {uid: "unknown" for uid in space_uids}
        self.candidates = {}
        self.since = {}
        self.frames = defaultdict(int)
        self.allow_initial_empty = bool(allow_initial_empty)
        self.initial_approved = set(initially_confirmed_empty_uids)
        self.absence_hold_seconds = float(absence_hold_seconds)
        self.blocked_confirm_seconds = max(0.3, float(blocked_confirm_seconds))
        self.last_vehicle_seen = {}
        self.had_vehicle = set()
        self.departure_verified = set()

    def update(self, raw: dict[str, str], now: float, departures=()) -> dict[str, str]:
        for uid in departures:
            if uid in self.states:
                self.departure_verified.add(uid)
        for uid, reported in raw.items():
            if uid not in self.states:
                continue
            desired = reported
            if reported == "occupied":
                self.last_vehicle_seen[uid] = now
                self.had_vehicle.add(uid)
                self.departure_verified.discard(uid)
            elif reported == "available":
                last_seen = self.last_vehicle_seen.get(uid)
                if last_seen is not None and now - last_seen < self.absence_hold_seconds:
                    # 検出が瞬断しただけでは占有解除しない
                    desired = "occupied"
                elif uid in self.had_vehicle and uid not in self.departure_verified:
                    # 車が見えなくなっただけでは退出と断定できない
                    desired = "unknown"
                elif (uid not in self.had_vehicle and not self.allow_initial_empty
                      and uid not in self.initial_approved):
                    # 初期フレームで見えない車があるかもしれない
                    desired = "unknown"
            elif reported == "unknown":
                # If a wheel pair is briefly lost but this space was recently
                # confirmed occupied, keep OCCUPIED for the configured hold.
                # A persistent uncertain view returns to UNKNOWN, never FREE.
                last_seen = self.last_vehicle_seen.get(uid)
                if last_seen is not None and now - last_seen < self.absence_hold_seconds:
                    desired = "occupied"
            elif reported != "blocked":
                desired = "unknown"

            if desired != self.candidates.get(uid):
                self.candidates[uid] = desired
                self.since[uid] = now
                self.frames[uid] = 1
            else:
                self.frames[uid] += 1
            # A passing person / shadow-like false detection must not make
            # a space BLOCKED for a single short-lived YOLO prediction.
            min_seconds = (5.0 if desired == "available"
                           else self.blocked_confirm_seconds if desired == "blocked"
                           else 0.3)
            if desired == "blocked" and self.states[uid] == "available":
                # During the confirmation window a person might really be
                # present; don't continue showing a stale AVAILABLE status.
                self.states[uid] = "unknown"
            if self.frames[uid] >= 2 and now - self.since[uid] >= min_seconds:
                self.states[uid] = desired
        return self.states.copy()

class SupabaseWriter:
    """Supabase Authの管理者アカウントで更新。秘密鍵をブラウザーへ置かない。"""
    def __init__(self, url: str, key: str, email: str, password: str):
        self.url = url.rstrip("/")
        self.key = key
        self.email = email
        self.access_token = ""
        self.refresh_token = ""
        self.expires_at = 0.0
        self._sign_in(password)

    def _call(self, url: str, body: dict | list, token: str = "",
              prefer: str = "") -> dict:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if prefer:
            headers["Prefer"] = prefer
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=payload, headers=headers, method="POST")
        with request.urlopen(req, timeout=10) as response:
            data = response.read()
            return json.loads(data) if data else {}

    def _sign_in(self, password: str):
        response = self._call(
            f"{self.url}/auth/v1/token?grant_type=password",
            {"email": self.email, "password": password},
        )
        self._store_tokens(response)

    def _store_tokens(self, data):
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.expires_at = time.monotonic() + int(data.get("expires_in", 3600))

    def _ensure_token(self):
        if time.monotonic() + 60 < self.expires_at:
            return
        data = self._call(
            f"{self.url}/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": self.refresh_token},
        )
        self._store_tokens(data)

    def upsert(self, table: str, records: list[dict], conflict: str):
        if not records:
            return
        self._ensure_token()
        self._call(
            f"{self.url}/rest/v1/{table}?on_conflict={parse.quote(conflict, safe=',')}",
            records, token=self.access_token,
            prefer="resolution=merge-duplicates,return=minimal",
        )


def detector_boxes(result, width: int, height: int, allowed: set[str]) -> list[dict]:
    output = []
    if not result or result.boxes is None:
        return output
    names = result.names
    boxes = result.boxes
    ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(boxes)
    for bbox, class_id, score, track_id in zip(
        boxes.xyxy.cpu().tolist(), boxes.cls.int().cpu().tolist(),
        boxes.conf.cpu().tolist(), ids,
    ):
        raw_name = str(names[int(class_id)]).lower().strip().replace("-", "_")
        name = CLASS_ALIASES.get(raw_name, raw_name)
        if name not in allowed:
            continue
        x1, y1, x2, y2 = bbox
        # 下辺中央を車両が地面に接している位置の近似として用いる。
        point = (min(1., max(0., (x1 + x2) / (2 * width))),
                 min(1., max(0., y2 / height)))
        # 下端の接地位置が区画境界をまたぐ場合は、安全側に「未確認」。
        contact = [
            (min(1., max(0., (x1 + (x2-x1)*fraction) / width)),
             min(1., max(0., y2 / height)))
            for fraction in (0.25, 0.5, 0.75)
        ]
        output.append({"name": name, "point": point, "bottom_points": contact,
                       "track_id": track_id, "confidence": float(score), "bbox": bbox})
    return output



def mark_vehicle_overlap(blockers: list[dict], vehicles: list[dict]):
    """Mark blocker predictions merged into the vehicle silhouette as uncertain.

    A real person standing in front of a car can overlap the car too: do not
    silently mark the touched area free; downgrade it to UNKNOWN instead.
    """
    for blocker in blockers:
        box = blocker.get("bbox")
        if not box or len(box) != 4:
            continue
        bx1, by1, bx2, by2 = (float(value) for value in box)
        area = max(0., bx2-bx1) * max(0., by2-by1)
        if area <= 0:
            continue
        for vehicle in vehicles:
            vehicle_box = vehicle.get("bbox")
            if not vehicle_box or len(vehicle_box) != 4:
                continue
            vx1, vy1, vx2, vy2 = (float(value) for value in vehicle_box)
            overlap = (max(0., min(bx2, vx2) - max(bx1, vx1))
                       * max(0., min(by2, vy2) - max(by1, vy1))) / area
            if overlap >= 0.55:
                blocker["near_vehicle"] = True
                break
    return blockers


def classify_spaces(vehicles: list[dict], blockers: list[dict], zones: dict,
                    parked_track_ids: set[int] | None = None) -> dict[str, str]:
    """Prefer a *pair* of visible tyre contacts to the YOLO bounding-box edge.

    - Both tyre contacts in one zone AND a parked track => occupied candidate.
    - Moving/entering vehicle in a zone => UNKNOWN while it is passing through.
    - One/no wheel or wheels on different zones => uncertain, never free.
    - A person visually merged into the car => uncertain, not BLOCKED.
    The legacy non-camera data format (without 'wheel_points') is preserved
    for old recordings and unit-test fixtures.
    """
    occupied, blocked, uncertain = set(), set(), set()

    def put_legacy(detection, definite):
        center_uid = space_for(detection["point"], zones)
        points = detection.get("bottom_points") or [detection["point"]]
        touched = {space_for(point, zones) for point in points}
        touched.discard(None)
        if center_uid and (not touched or touched == {center_uid}):
            definite.add(center_uid)
        elif touched:
            uncertain.update(touched)
            if center_uid:
                uncertain.add(center_uid)
        elif center_uid:
            definite.add(center_uid)

    for vehicle in vehicles:
        # Camera detections explicitly contain wheel_points, even if no
        # reliable wheel pair is visible. Do not call a box edge a tyre.
        if "wheel_points" not in vehicle:
            put_legacy(vehicle, occupied)
            continue
        wheels = vehicle["wheel_points"] or []
        wheel_zones = [space_for(point, zones) for point in wheels]
        touched = {uid for uid in wheel_zones if uid is not None}
        matched_wheels = (len(wheels) >= 2 and len(touched) == 1
                          and all(uid is not None for uid in wheel_zones))
        # When active tracking information is present, passing traffic must
        # never be described as a parked car. Legacy video/offline callers
        # intentionally omit parked_track_ids for backward compatibility.
        track_id = vehicle.get("track_id")
        is_parked = (parked_track_ids is None or
                     track_id is not None and int(track_id) in parked_track_ids)
        # Field mode provides a lower-body zone estimate as a fallback:
        # the car must ALSO have remained stationary long enough.
        candidate = vehicle.get("zone_candidate")
        zone_touched = set(vehicle.get("zone_touched", []))
        if "zone_candidate" in vehicle:
            if is_parked and candidate and (
                    not matched_wheels or candidate in touched):
                occupied.add(candidate)
            else:
                uncertain.update(zone_touched)
                if candidate:
                    uncertain.add(candidate)
            continue
        if matched_wheels and is_parked:
            occupied.update(touched)
        else:
            uncertain.update(touched)
            # Legacy input without image dimensions.
            if not touched:
                for point in vehicle.get("bottom_points", []):
                    uid = space_for(point, zones)
                    if uid is not None:
                        uncertain.add(uid)

    for blocker in blockers:
        put_legacy(blocker, uncertain if blocker.get("near_vehicle") else blocked)
    return {
        uid: ("occupied" if uid in occupied else
              "unknown" if uid in uncertain else
              "blocked" if uid in blocked else "available")
        for uid in zones
    }


def infer_frame(vehicle_model, obstacle_model, frame, confidence: float,
                tracker_file: str = DEFAULT_TRACKER, image_size: int = 960,
                occupancy_confidence: float = 0.35):
    """モデルが使えるか確認しながら1フレームを判定する。車両IDはByteTrackで取得する。"""
    height, width = frame.shape[:2]
    results = vehicle_model.track(
        frame, persist=True, tracker=tracker_file, conf=confidence,
        imgsz=image_size, verbose=False,
    )
    vehicles = detector_boxes(results[0], width, height, VEHICLE_NAMES)
    for vehicle in vehicles:
        # Actual image features are checked for two tyre-like circles.
        # No confident pair => []; never invent wheel locations from a box.
        contacts = estimate_wheel_contacts(frame, vehicle["bbox"])
        vehicle["wheel_points"] = contacts
    # 追跡器には低確信度の検出も渡すが、占有判定には最低限の信頼を求める。
    # IDの連続性向上のため、検出した車両そのものはここでは除外しない。
    blockers = [d for d in detector_boxes(results[0], width, height, BLOCKING_NAMES)
                if d["confidence"] >= occupancy_confidence]
    if obstacle_model:
        results_extra = obstacle_model.predict(frame, conf=confidence, verbose=False)
        blockers.extend(detector_boxes(results_extra[0], width, height, BLOCKING_NAMES))
    mark_vehicle_overlap(blockers, vehicles)
    return vehicles, blockers


def overlay(frame, zones, statuses, vehicle_detections, obstacles, phases=None):
    """YOLOの認識結果を、研究発表で見返せる映像に描画する。

    検出の囲み・クラス名・信頼度・追跡ID・駐車状態を必ず区別する。
    OpenCVの文字機能は日本語非対応なので、英語ラベルと凡例を用いる。
    生のカメラ画像は変更せず、別の画像を返す。
    """
    import cv2

    height, width = frame.shape[:2]
    phases = phases or {}
    # 下部に説明帯を足し、白飛びした画像の上でも文字を読めるようにする。
    view = cv2.copyMakeBorder(
        frame.copy(), 0, 98, 0, 0, cv2.BORDER_CONSTANT, value=(22, 25, 29)
    )
    labels = {
        "available": ("AVAILABLE", (70, 195, 70)),
        "occupied": ("OCCUPIED", (0, 155, 255)),
        "blocked": ("BLOCKED", (65, 70, 235)),
        "unknown": ("UNKNOWN", (195, 195, 195)),
    }

    def draw_text(message, pos, scale=.52, color=(255, 255, 255), thickness=1):
        x, y = int(pos[0]), int(pos[1])
        x, y = max(4, x), max(16, y)
        cv2.putText(view, message, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
        cv2.putText(view, message, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, color, thickness, cv2.LINE_AA)

    for uid, polygon in zones.items():
        points = [(int(x * width), int(y * height)) for x, y in polygon]
        state, color = labels.get(statuses.get(uid, "unknown"), labels["unknown"])
        for first, second in zip(points, points[1:] + points[:1]):
            cv2.line(view, first, second, color, 3, cv2.LINE_AA)
        draw_text(f"{uid}: {state}", points[0], .58, color, 2)

    for detection in vehicle_detections + obstacles:
        bbox = detection.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (int(v) for v in bbox)
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        is_obstacle = detection in obstacles
        color = ((125, 125, 125) if detection.get("near_vehicle") else (70, 80, 240)) if is_obstacle else (70, 255, 80)
        cv2.rectangle(view, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        ident = detection.get("track_id")
        track_label = ("ID" + str(ident)) if ident is not None else "ID?"
        confidence = detection.get("confidence")
        value = f"{float(confidence):.2f}" if confidence is not None else "-"
        phase = phases.get(int(ident), "") if ident is not None else ""
        line = f"{detection.get('name', 'object')} {track_label} {value}"
        if detection.get("near_vehicle"):
            line += " UNCERTAIN (near vehicle)"
        if phase:
            line += f" {phase.upper()}"
        text_y = y1 - 7 if y1 >= 31 else min(height - 8, y2 + 17)
        draw_text(line, (x1, text_y), .48, color, 2)
        if not is_obstacle:
            zone_candidate = detection.get("zone_candidate")
            if zone_candidate:
                draw_text(f"ZONE EST: {zone_candidate}", (x1, min(height - 8, y2 + 16)),
                          .44, (245, 210, 80), 1)
            wheel_points = detection.get("wheel_points") or []
            for nx, ny in wheel_points:
                px, py = round(nx * width), round(ny * height)
                cv2.circle(view, (px, py), 7, (255, 0, 255), 2, cv2.LINE_AA)
                draw_text("WHEEL EST.", (px + 8, py - 6), .35, (255, 0, 255), 1)

    # RECではなくYOLO ANALYSIS。推論が間に合わずコマを複製しても
    # 「毎フレーム新しい判定が走った」と誤解されないように時刻を固定。
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    draw_text(f"YOLO ANALYSIS AT {stamp}", (12, height + 25), .58, (255, 255, 255), 2)
    draw_text(
        f"VEHICLES: {len(vehicle_detections)}   BLOCKERS: {len(obstacles)}"
        "   GREEN=vehicle   RED=obstacle",
        (12, height + 50), .48,
    )
    draw_text(
        "SPACE: GREEN=available ORANGE=occupied RED=blocked GRAY=unknown",
        (12, height + 72), .45,
    )
    draw_text("Magenta WHEEL EST. = image-based estimate, not verified tyre keypoint",
              (12, height + 91), .40, (180, 185, 190))
    # Keep the timing warning in the PowerShell log; repeated video frames
    # still carry the same YOLO ANALYSIS timestamp.

    return view


def main():
    parser = argparse.ArgumentParser(description="YOLO駐車場カメラ監視・車両追跡")
    parser.add_argument("--config", default="config.json", help="撮影範囲とクラウド設定")
    parser.add_argument("--preview", action="store_true", help="検知範囲と状態を表示する")
    parser.add_argument("--dry-run", action="store_true", help="クラウドに書き込まず試す")
    args = parser.parse_args()
    config = load_config(args.config)
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as ex:
        raise SystemExit("必要なライブラリがありません。python -m pip install -r requirements.txt") from ex

    source = config["source"]
    req_w, req_h, req_fps = capture_preferences(config)
    camera = open_camera(cv2, source, config.get("camera_backend", "auto"),
                         config.get("camera_manual_exposure"),
                         req_w, req_h, req_fps)
    if not camera.isOpened():
        raise SystemExit("カメラを開けません。config.json の source を確認してください")
    # 録画ファイルを誤って「今現在の駐車場」として公開しないための防止策。
    if isinstance(source, str) and Path(source).suffix.lower() in {
        ".mp4", ".mov", ".avi", ".mkv", ".webm"
    } and not args.dry_run:
        raise SystemExit("録画ファイルはリアルタイム公開できません。analyze_video.py を使用してください")
    vehicle_model = YOLO(config.get("vehicle_model", "yolo11n.pt"))
    obstacle_path = config.get("obstacle_model")
    obstacle_model = YOLO(obstacle_path) if obstacle_path else None

    writer = None
    if not args.dry_run:
        print("Supabaseの管理者アカウントでログインします。")
        email = input("管理者メールアドレス: ").strip()
        password = getpass("パスワード（画面に表示されません）: ")
        writer = SupabaseWriter(config["supabase_url"], config["publishable_key"], email, password)
        del password

    zones = config["space_zones"]
    observer = SpaceObserver(
        zones,
        allow_initial_empty=bool(config.get("allow_unverified_initial_empty", False)),
        absence_hold_seconds=float(config.get("occupied_hold_seconds", 8)),
        blocked_confirm_seconds=float(config.get("blocked_confirm_seconds", 2)),
        initially_confirmed_empty_uids=config.get("initially_confirmed_empty_uids", []),
    )
    tracks = VehicleTracker(config["facility_id"], config["camera_id"],
                            float(config.get("park_seconds", 5)),
                            lost_seconds=float(config.get("reid_window_seconds", 12)))
    snapshots = SnapshotPublisher(writer, config)
    stable_ids = StableIdMatcher(max_missing=float(config.get("reid_window_seconds", 12)))
    last_push, last_print = 0., 0.
    previous_statuses = None
    pending_sessions = {}  # 出口通過・追跡消失など、画面から消える直前のイベントも保存する
    # 画像取得とローカル録画は別スレッド。重いYOLO処理中も映像を保存する。
    recording = RecordingCamera(
        camera, cv2,
        fps=int(config.get("recording_fps", 10)),
        segment_seconds=int(config.get("recording_segment_seconds", 600)),
    )
    sequence = 0
    visual_recorder = None
    try:
        folder = recording.start()
        # 設定したカメラと区画座標の画角が一致するかを、映像取得後に必ず確認。
        # これが失敗した場合はライブ送信せず安全に録画を閉じる。
        first_frame, sequence = recording.next_frame(sequence)
        first_h, first_w = first_frame.shape[:2]
        assert_calibrated_view(config, first_w, first_h)
        print(f"【撮影サイズ】{first_w} x {first_h}（元画像を切り抜かずに解析・録画）")
        print("【画角】iPhone/Camoのレンズ・ズーム・トリミング設定は端末側をご確認ください。")
        # 生映像とYOLO判定済み映像は同じ実験フォルダに別々に保存する。
        visual_recorder = YoloVisualRecorder(
            folder, cv2, session_start=recording._started,
            fps=int(config.get("yolo_recording_fps", 5)),
            segment_seconds=int(config.get("recording_segment_seconds", 600)),
        )
        print(f"【録画保存先】{folder}")
        print("【録画について】生映像とYOLO判定付き動画をPC内に別々に保存します")
        while True:
            frame, sequence = recording.next_frame(sequence)
            try:
                snapshots.publish(frame)
            except (error.URLError, OSError, ValueError, KeyError) as exc:
                print(f"カメラ写真の共有に失敗: {type(exc).__name__}")
            vehicles, blockers = infer_frame(
                vehicle_model, obstacle_model, frame,
                float(config.get("tracking_confidence", 0.15)),
                tracker_file=str(config.get("tracker_file", DEFAULT_TRACKER)),
                image_size=int(config.get("image_size", 960)),
                occupancy_confidence=float(config.get("confidence", 0.35)),
            )
            now = time.monotonic()
            vehicles = stable_ids.update(vehicles, now, frame=frame)
            # Keep tracking point independent of flickering wheel detection.
            # Lower-body zones take over only the *space* mapping.
            annotate_vehicle_zones(vehicles, zones, inside, frame.shape)
            events = tracks.update(vehicles, zones, config.get("exit_zone", []), now)
            for event in events:
                pending_sessions[event["session_id"]] = event
            # 区画占有だけには信頼度が低い検出を使わない
            occupancy_vehicles = [d for d in vehicles
                                  if d["confidence"] >= float(config.get("confidence", 0.35))]
            parked_ids = {int(track_id) for track_id, entry in tracks.vehicles.items()
                          if entry.phase == "parked"}
            raw = classify_spaces(occupancy_vehicles, blockers, zones,
                                  parked_track_ids=parked_ids)
            departures = [event["space_uid"] for event in events
                          if event["phase"] == "exiting" and event.get("space_uid")]
            statuses = observer.update(raw, now, departures=departures)
            changed = statuses != previous_statuses
            if changed:
                recording.log_status(statuses)
            # ネットワーク更新が遅くても、推論直後の判定映像を先に保存する。
            phases = {int(tid): record.phase for tid, record in tracks.vehicles.items()}
            annotated = overlay(frame, zones, statuses, vehicles, blockers, phases)
            visual_recorder.write(annotated, now=time.monotonic())
            should_send = changed or now - last_push >= 5 or (bool(pending_sessions) and now - last_push >= 1)
            if should_send:
                if writer:
                    rows = [{
                        "facility_id": config["facility_id"], "space_uid": uid,
                        "status": status, "confidence": None,  # 測定していない確信度を捏造しない
                        "source": "yolo", "checked_at": utc_now(),
                    } for uid, status in statuses.items()]
                    try:
                        writer.upsert("parking_live_status", rows, "facility_id,space_uid")
                        # 追跡IDは同じカメラ稼働中だけ有効。車の画像は保存しない。
                        session_rows = {entry.session_id: entry.row() for entry in tracks.vehicles.values()}
                        for sid, event in pending_sessions.items():
                            session_rows.setdefault(sid, event)  # 終了済みイベントのみ復元する
                        writer.upsert("parking_vehicle_sessions", list(session_rows.values()), "session_id")
                        pending_sessions.clear()
                    except (error.URLError, error.HTTPError, OSError, KeyError) as exc:
                        print(f"クラウド共有に失敗: {exc}（認証・権限・通信をご確認ください）")
                if changed or now - last_print >= 5:
                    print(" / ".join(f"{uid}={STATUS_NAMES[status]}" for uid, status in statuses.items()))
                    last_print = now
                if not writer:
                    pending_sessions.clear()
                previous_statuses, last_push = statuses.copy(), now
            # 非プレビューでも上で保存済み。画面には同じ判定結果を表示する。
            if args.preview:
                max_w = int(config.get("camera_preview_max_width", 1280))
                max_h = int(config.get("camera_preview_max_height", 800))
                shown_w, shown_h = fit_preview_dimensions(
                    annotated.shape[1], annotated.shape[0], max_w, max_h
                )
                # 画角維持・切り抜きなし。プレビューだけ縦横比を保ち縮小。
                view = (cv2.resize(annotated, (shown_w, shown_h),
                                   interpolation=cv2.INTER_AREA)
                        if (shown_w, shown_h) != (annotated.shape[1], annotated.shape[0])
                        else annotated)
                cv2.imshow("Parking camera (q to quit)", view)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        # 再生可能なMP4にするため、停止時には両方のライターを閉じる。
        if visual_recorder is not None:
            visual_recorder.close()
        recording.close()  # 停止・通信断時にも動画とCSVを確定する。
        camera.release()
        if args.preview:
            cv2.destroyAllWindows()
        if recording.folder:
            print(f"【録画を見返す】{recording.folder}")


if __name__ == "__main__":
    try:
        main()
    except error.HTTPError as exc:
        sys.exit(f"クラウド認証・保存に失敗しました（HTTP {exc.code}）。ログインと権限を確認してください")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.exit(f"設定を確認してください: {exc}")
