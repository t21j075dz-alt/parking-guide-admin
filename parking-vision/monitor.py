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
from math import hypot
from statistics import median
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
from person_stability import PersonIdStabilizer
from vehicle_zone import annotate_vehicle_zones, is_monitored_vehicle
from night_vision import inference_frame, is_low_light
from night_vehicle_evidence import NightVehicleEvidenceGate
from parking_diagnostics import ParkingDiagnosticRecorder
from zone_geometry import normalize_corners, audit_zones

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
        if len(polygon) == 4:
            # Old calibrations may have saved corner clicks in crossing order.
            # Repair the ordering in memory without rewriting config.json.
            try:
                ordered = normalize_corners(polygon)
            except ValueError as exc:
                raise ValueError(f"{uid} の四隅を再登録してください: {exc}") from exc
            if ordered != polygon:
                print(f"【区画座標の補正】{uid} の4点を正しい周回順に整えました（元ファイルは維持）")
            zones[uid] = ordered
    for warning in audit_zones(zones):
        print(f"【区画の位置に注意】{warning}")
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
    if content.get("night_vision_mode", "auto") not in ("auto", "on", "off"):
        raise ValueError("night_vision_mode は auto / on / off のどれかを選んでください")
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
    locations: deque = field(default_factory=lambda: deque(maxlen=150))
    zone_history: deque = field(default_factory=lambda: deque(maxlen=150))
    stationary: bool = False
    smoothed_uid: str | None = None
    zone_votes: int = 0
    park_anchor: tuple[float, float] | None = None

    def _stable_space(self, uid: str | None, now: float) -> str | None:
        """Do not erase a stall vote because wheels are missing for one frame.

        Only recorded observations within 4.5 seconds count. A competing
        stall or too few votes gives UNKNOWN, never a best-guess occupancy.
        """
        self.zone_history.append((now, uid))
        recent = [zone for clock, zone in self.zone_history if now - clock <= 4.5]
        votes = {zone: recent.count(zone) for zone in set(recent) if zone is not None}
        ordered = sorted(votes.items(), key=lambda item: item[1], reverse=True)
        top, count = ordered[0] if ordered else (None, 0)
        second = ordered[1][1] if len(ordered) > 1 else 0
        self.zone_votes = count
        if (top and count >= 3 and count > second * 2 and
                count >= 0.32 * len(recent)):
            return top
        return None

    def _is_stationary(self, now: float) -> bool:
        """Robust to occasional YOLO box jitter, but not a passing car.

        Requires more than 1.8 seconds of observations with an unmoving
        endpoint and most points near the median. No vehicle ID means no
        stationary state and therefore no new OCCUPIED detection.
        """
        recent = [(t, p) for t, p in self.locations if now - t <= 3.5]
        if len(recent) < 3 or recent[-1][0] - recent[0][0] < 1.8:
            return False
        xs = [p[0] for _, p in recent]
        ys = [p[1] for _, p in recent]
        center = (median(xs), median(ys))
        distances = sorted(hypot(p[0] - center[0], p[1] - center[1])
                           for _, p in recent)
        p80 = distances[min(len(distances) - 1, int(.8 * (len(distances) - 1)))]
        # A continuously moving car can have a compact box for 1-2 frames;
        # compare the endpoints as well as spread over a >=1.8-second window.
        return p80 <= .022 and hypot(xs[-1] - xs[0], ys[-1] - ys[0]) <= .028

    def observe(self, point: tuple[float, float], uid: str | None,
                in_exit: bool, now: float, park_seconds: float):
        self.seen_monotonic = now
        self.last_seen_at = utc_now()
        self.position_x, self.position_y = point
        self.locations.append((now, point))
        self.stationary = self._is_stationary(now)
        self.smoothed_uid = self._stable_space(uid, now)
        if uid is None and self.phase in {"entering", "moving"}:
            self.arrived_from_outside = True

        if self.phase in {"entering", "moving"}:
            # Require multiple observations of the same zone and at least
            # park_seconds of a stable position, even if raw zone estimates
            # temporarily disappear on shadows or camera edges.
            if self.smoothed_uid and self.stationary:
                if self.candidate_uid != self.smoothed_uid:
                    self.candidate_uid = self.smoothed_uid
                    self.candidate_since = now
                    self.candidate_started_at = utc_now()
                elif now - self.candidate_since >= park_seconds:
                    self.phase, self.space_uid = "parked", self.smoothed_uid
                    self.park_anchor = point
                    # Camera started while already parked => start unknown.
                    self.parked_at = (self.candidate_started_at or utc_now()) if self.arrived_from_outside else None
            else:
                # A few lost zone samples are covered by smoothed_uid;
                # real motion resets parking confirmation.
                self.candidate_uid = None
                self.candidate_started_at = None
                if self.phase == "entering" and len(self.locations) > 3:
                    self.phase = "moving"

        if self.phase == "parked":
            moved_from_space = (self.park_anchor is not None
                                and hypot(point[0] - self.park_anchor[0],
                                          point[1] - self.park_anchor[1]) >= .045)
            # Missing zone estimates ALONE are not evidence of departure.
            if not self.stationary and moved_from_space and uid != self.space_uid:
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
            detected["zone_smoothed"] = entry.smoothed_uid
            detected["stationary"] = entry.stationary
            detected["zone_votes"] = entry.zone_votes
            # If a reliably parked vehicle briefly loses its wheel and
            # lower-body position, keep the previously verified stall,
            # unless this frame gives contradictory zone evidence.
            detected["confirmed_parked_space"] = (
                entry.space_uid if entry.phase == "parked"
                and (uid in (None, entry.space_uid))
                and detected.get("zone_basis") != "conflict"
                and (entry.stationary or uid == entry.space_uid)
                else None)
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
                 blocked_confirm_seconds=2.0,
                 initial_empty_deadline_epoch=None):
        self.states = {uid: "unknown" for uid in space_uids}
        self.candidates = {}
        self.since = {}
        self.frames = defaultdict(int)
        self.allow_initial_empty = bool(allow_initial_empty)
        self.initial_approved = set(initially_confirmed_empty_uids)
        # Explicitly verified empty spaces are valid only within a short
        # operator-confirmed time window. Legacy configs without a deadline
        # keep their original behavior for compatibility.
        self.initial_empty_deadline_epoch = initial_empty_deadline_epoch
        self.absence_hold_seconds = float(absence_hold_seconds)
        self.blocked_confirm_seconds = max(0.3, float(blocked_confirm_seconds))
        self.last_vehicle_seen = {}
        self.had_vehicle = set()
        self.departure_verified = set()

    def update(self, raw: dict[str, str], now: float, departures=()) -> dict[str, str]:
        if (self.initial_empty_deadline_epoch is not None
                and time.time() >= float(self.initial_empty_deadline_epoch)):
            # An old human confirmation cannot be reused as evidence of
            # empty spaces hours later or after a different car arrives.
            self.initial_approved.clear()
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
    """Camera bottom-footprint only. Parked track and unique zone required."""
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
        # Actual camera detections have zone_candidate based solely on the
        # lower vehicle silhouette. Never use wheel_points, even in old JSON.
        if "zone_candidate" not in vehicle:
            point_uid = space_for(vehicle["point"], zones)
            touched = {space_for(p, zones) for p in
                       (vehicle.get("bottom_points") or [vehicle["point"]])}
            touched.discard(None)
            raw_id = vehicle.get("track_id")
            is_parked = (parked_track_ids is None or
                         raw_id is not None and int(raw_id) in parked_track_ids)
            if point_uid and touched <= {point_uid} and is_parked:
                occupied.add(point_uid)
            else:
                uncertain.update(touched)
                if point_uid:
                    uncertain.add(point_uid)
            continue

        candidate = vehicle.get("zone_candidate")
        touched = set(vehicle.get("zone_touched") or [])
        if vehicle.get("night_verified") is False:
            uncertain.update(touched)
            if candidate:
                uncertain.add(candidate)
            continue
        raw_id = vehicle.get("track_id")
        is_parked = (parked_track_ids is None or
                     raw_id is not None and int(raw_id) in parked_track_ids)
        confirmed = vehicle.get("confirmed_parked_space")
        chosen = candidate or confirmed
        if is_parked and chosen:
            occupied.add(chosen)
            uncertain.update(touched - {chosen})
        else:
            uncertain.update(touched)
            if candidate:
                uncertain.add(candidate)
            if confirmed:
                uncertain.add(confirmed)
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
                occupancy_confidence: float = 0.35,
                night_vision_mode: str = "auto"):
    """モデルが使えるか確認し、車体底面判定で追跡する。"""
    height, width = frame.shape[:2]
    model_frame, _, _ = inference_frame(frame, mode=night_vision_mode)
    results = vehicle_model.track(
        model_frame, persist=True, tracker=tracker_file, conf=confidence,
        imgsz=image_size, verbose=False,
    )
    vehicles = detector_boxes(results[0], width, height, VEHICLE_NAMES)
    # Only the bottom of the vehicle detection box decides stall location.
    # Untrained Hough wheel-circle estimates are not executed.
    # 追跡器には低確信度の検出も渡すが、占有判定には最低限の信頼を求める。
    # IDの連続性向上のため、検出した車両そのものはここでは除外しない。
    blockers = [d for d in detector_boxes(results[0], width, height, BLOCKING_NAMES)
                if d["confidence"] >= occupancy_confidence]
    if obstacle_model:
        results_extra = obstacle_model.predict(model_frame, conf=confidence, verbose=False)
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
        unverified = (not is_obstacle and (detection.get("monitored") is False
                        or detection.get("night_verified") is False))
        color = ((125, 125, 125) if detection.get("near_vehicle") else (70, 80, 240)) if is_obstacle else (135, 145, 155) if unverified else (70, 255, 80)
        cv2.rectangle(view, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        ident = detection.get("track_id")
        if is_obstacle and detection.get("name") == "person":
            track_label = ("ID" + str(ident)
                           if detection.get("person_confirmed") and ident is not None
                           else "ID:CHECKING")
        elif is_obstacle:
            track_label = ""  # traffic cones / carts do not have person IDs
        else:
            track_label = ("ID" + str(ident)) if ident is not None else "ID?"
        confidence = detection.get("confidence")
        value = f"{float(confidence):.2f}" if confidence is not None else "-"
        phase = phases.get(int(ident), "") if ident is not None else ""
        detected_name = detection.get('name', 'object')
        if unverified:
            detected_name += "? (UNVERIFIED)"
        line = f"{detected_name} {track_label} {value}"
        if detection.get("near_vehicle"):
            line += " UNCERTAIN (near vehicle)"
        if phase:
            line += f" {phase.upper()}"
        if not is_obstacle and detection.get("monitored") is False:
            line += " IGNORED: OUTSIDE CAMERA ZONES"
        elif not is_obstacle and detection.get("night_verified") is False:
            line += " NIGHT: NO APPROACH EVIDENCE"
        text_y = y1 - 7 if y1 >= 31 else min(height - 8, y2 + 17)
        draw_text(line, (x1, text_y), .48, color, 2)
        if not is_obstacle:
            zone_candidate = detection.get("zone_candidate")
            phase_name = phases.get(int(ident), "") if ident is not None else ""
            reported = zone_candidate or detection.get("zone_smoothed") or "?"
            diagnostic = (f"ZONE {reported} ({detection.get('zone_basis', '?')}) "
                          f"VOTES {detection.get('zone_votes', 0)} "
                          f"STILL {int(bool(detection.get('stationary')))} "
                          f"{phase_name.upper()}")
            draw_text(diagnostic, (x1, min(height - 8, y2 + 16)),
                      .43, (245, 210, 80), 1)
            # 車体底面方式に統一。ホイール推定点は表示しない。

    # RECではなくYOLO ANALYSIS。推論が間に合わずコマを複製しても
    # 「毎フレーム新しい判定が走った」と誤解されないように時刻を固定。
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    draw_text(f"YOLO ANALYSIS AT {stamp}", (12, height + 25), .58, (255, 255, 255), 2)
    draw_text(
        f"VEHICLES VERIFIED: {sum(1 for v in vehicle_detections if v.get('night_verified', True) and v.get('monitored', True))}"
        f" / DETECTED: {len(vehicle_detections)}   BLOCKERS: {len(obstacles)}"
        "   GREEN=verified GRAY=unverified RED=obstacle",
        (12, height + 50), .48,
    )
    draw_text(
        "SPACE: GREEN=available ORANGE=occupied RED=blocked GRAY=unknown",
        (12, height + 72), .45,
    )
    draw_text("ZONE = CAR BOTTOM FOOTPRINT / NO WHEEL-CIRCLE ESTIMATION",
              (12, height + 91), .40, (180, 185, 190))
    # Keep the timing warning in the PowerShell log; repeated video frames
    # still carry the same YOLO ANALYSIS timestamp.

    return view


def main():
    parser = argparse.ArgumentParser(description="YOLO駐車場カメラ監視・車両追跡")
    parser.add_argument("--config", default="config.json", help="撮影範囲とクラウド設定")
    parser.add_argument("--preview", action="store_true", help="検知範囲と状態を表示する")
    parser.add_argument("--dry-run", action="store_true", help="クラウドに書き込まず試す")
    parser.add_argument("--video", default="", help="録画動画を実時間に合わせてYOLO判定する")
    parser.add_argument("--demo-publish", action="store_true",
                        help="録画実演専用施設だけに判定を共有（実カメラ施設とは分離）")
    parser.add_argument("--verified-empty", default="",
                        help="録画の冒頭で目視確認した空き区画ID（カンマ区切り、省略可能）")
    args = parser.parse_args()
    config = load_config(args.config)
    from video_demo_support import (
        require_demo_mode, parse_verified_empty, draw_demo_watermark,
        verify_overlay_with_operator, demo_status_rows, set_demo_visibility,
    )
    require_demo_mode(config, args)
    video_mode = bool(args.video)
    if args.verified_empty and not video_mode:
        raise ValueError("--verified-empty は録画実演用です")
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as ex:
        raise SystemExit("必要なライブラリがありません。python -m pip install -r requirements.txt") from ex

    camera = None
    if video_mode:
        from video_replay import VideoReplay
        recording = VideoReplay(args.video, cv2)
        print("【入力】録画映像を再生しながらYOLO推論（実カメラは使用しません）")
        print("【重要】動画の状態は実際の駐車場の現在の空きではありません。")
    else:
        source = config["source"]
        req_w, req_h, req_fps = capture_preferences(config)
        camera = open_camera(cv2, source, config.get("camera_backend", "auto"),
                             config.get("camera_manual_exposure"),
                             req_w, req_h, req_fps)
        if not camera.isOpened():
            raise SystemExit("カメラを開けません。config.json の source を確認してください")
        if isinstance(source, str) and Path(source).suffix.lower() in {
            ".mp4", ".mov", ".avi", ".mkv", ".webm"
        } and not args.dry_run:
            raise SystemExit("録画ファイルは実カメラとして公開できません。--video を使用してください")
    vehicle_model = YOLO(config.get("vehicle_model", "yolo11n.pt"))
    obstacle_path = config.get("obstacle_model")
    obstacle_model = YOLO(obstacle_path) if obstacle_path else None

    writer = None
    if not args.dry_run and (not video_mode or args.demo_publish):
        print("Supabaseの管理者アカウントでログインします。")
        email = input("管理者メールアドレス: ").strip()
        password = getpass("パスワード（画面に表示されません）: ")
        writer = SupabaseWriter(config["supabase_url"], config["publishable_key"], email, password)
        del password

    zones = config["space_zones"]
    initial_empty_deadline = None
    if config.get("initial_empty_verified_at"):
        try:
            stamp = datetime.fromisoformat(str(config["initial_empty_verified_at"]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone missing")
            ttl = max(0, min(900, int(config.get("initial_empty_valid_seconds", 900))))
            initial_empty_deadline = stamp.timestamp() + ttl
            if time.time() >= initial_empty_deadline:
                print("【初期空車確認は期限切れ】空車を勝手に認めません。現地で再確認してください。")
        except (TypeError, ValueError, OverflowError) as exc:
            initial_empty_deadline = 0
            print(f"【初期空車確認が無効】確認日時を解釈できません: {type(exc).__name__}")
    if video_mode and args.verified_empty:
        # Legacy option no longer needed: this is an isolated replay whose
        # default is all AVAILABLE. Detecting a car changes that to UNKNOWN
        # during the first five seconds of verification.
        parse_verified_empty(args.verified_empty, zones)
        print("【録画実演】初期6区画はすべて「空き」。"
              "車体底面を検知した区画は確定まで「確認中」とします。"
              "-VerifiedEmpty の指定は不要です。")
    confirmed_empty = ([] if video_mode else
                       config.get("initially_confirmed_empty_uids", []))
    from recorded_parking_states import RecordedParkingStateMachine
    demo_machine = RecordedParkingStateMachine(zones) if video_mode else None
    previous_demo_phases = None
    observer = SpaceObserver(
        zones,
        allow_initial_empty=(False if video_mode else bool(config.get("allow_unverified_initial_empty", False))),
        absence_hold_seconds=float(config.get("occupied_hold_seconds", 8)),
        blocked_confirm_seconds=float(config.get("blocked_confirm_seconds", 2)),
        initially_confirmed_empty_uids=confirmed_empty,
        initial_empty_deadline_epoch=(None if video_mode else initial_empty_deadline),
    )
    tracks = VehicleTracker(config["facility_id"], config["camera_id"],
                            float(config.get("park_seconds", 5)),
                            lost_seconds=float(config.get("reid_window_seconds", 12)))
    snapshots = None if video_mode else SnapshotPublisher(writer, config)
    stable_ids = StableIdMatcher(max_missing=float(config.get("reid_window_seconds", 12)))
    stable_people = PersonIdStabilizer(visible_seconds=1.0)
    night_evidence = NightVehicleEvidenceGate(
        lifetime_seconds=float(config.get("reid_window_seconds", 12)))
    last_push, last_print = 0., 0.
    previous_statuses = None
    pending_sessions = {}  # 出口通過・追跡消失など、画面から消える直前のイベントも保存する
    # 実カメラのときだけ別スレッドで生映像を録画する。
    # 動画再生のときはVideoReplayを用いて元動画を変更せず推論する。
    if not video_mode:
        recording = RecordingCamera(
            camera, cv2,
            fps=int(config.get("recording_fps", 10)),
            segment_seconds=int(config.get("recording_segment_seconds", 600)),
        )
    sequence = 0
    visual_recorder = None
    diagnostic_recorder = None
    demo_visible = False
    try:
        folder = recording.start()
        diagnostic_recorder = ParkingDiagnosticRecorder(folder)
        # 設定したカメラと区画座標の画角が一致するかを、映像取得後に必ず確認。
        # これが失敗した場合はライブ送信せず安全に録画を閉じる。
        first_frame, sequence = recording.next_frame(sequence)
        first_h, first_w = first_frame.shape[:2]
        assert_calibrated_view(config, first_w, first_h)
        print(f"【映像サイズ】{first_w} x {first_h}（元画像を切り抜かずに解析）")
        if video_mode:
            if not verify_overlay_with_operator(first_frame, zones, cv2):
                print("【実演中止】録画と6区画が一致しないため共有しません。")
                return
            print("【録画実演の初期状態】全区画「空き」から開始します。"
                  "車両が検出された区画は、5秒間の確定まで「確認中」に切り替わります。")
            if writer:
                set_demo_visibility(writer, False)
                print("【録画実演】判定データの送信後、この実験施設だけ共有をONにします。")
            # 確認画面や認証にかかった時間は動画の再生時間に含めない。
            recording.reset_clock_after_confirmation()
        print("【画角】iPhone/Camoのレンズ・ズーム・トリミング設定は端末側をご確認ください。")
        # 生映像とYOLO判定済み映像は同じ実験フォルダに別々に保存する。
        visual_recorder = YoloVisualRecorder(
            folder, cv2, session_start=recording._started,
            fps=int(config.get("yolo_recording_fps", 5)),
            segment_seconds=int(config.get("recording_segment_seconds", 600)),
        )
        print(f"【録画保存先】{folder}")
        if video_mode:
            print("【保存】元動画はそのまま。YOLO判定付き動画とCSVを研究フォルダに保存します。")
        else:
            print("【録画について】生映像とYOLO判定付き動画をPC内に別々に保存します")
        print("【原因の特定】同じフォルダの「駐車区画_判定診断.csv」に位置・停止・区画投票を記録します")
        while True:
            frame, sequence = recording.next_frame(sequence)
            if frame is None:  # 録画動画の終端。実カメラの場合はNoneにならない。
                break
            if snapshots:
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
                night_vision_mode=str(config.get("night_vision_mode", "auto")),
            )
            now = time.monotonic()
            # Video replay uses footage timestamps for identity and motion.
            # CPU stalls do not become fake 5-second vehicle observations.
            track_now = recording.frame_index / recording.fps if video_mode else now
            # Human IDs are independent from vehicle IDs. A person detected
            # only once receives no displayed ID, and old YOLO raw IDs are
            # not exposed or uploaded as person identities.
            stable_people.update(blockers, track_now)
            # Map each raw vehicle to the parking area *before* stable ID
            # association. Nighttime reflections and distant parked cars
            # otherwise pollute ID memory and swap with actual incoming cars.
            annotate_vehicle_zones(vehicles, zones, inside, frame.shape)
            monitored_raw = []
            ignored = []
            for vehicle in vehicles:
                relevant = is_monitored_vehicle(
                    vehicle, zones, inside, config.get("entry_zone", []),
                    config.get("exit_zone", []))
                vehicle["monitored"] = relevant
                if relevant:
                    monitored_raw.append(vehicle)
                else:
                    vehicle["ignored_raw_track_id"] = vehicle.get("track_id")
                    vehicle["track_id"] = None  # Not a managed vehicle session.
                    ignored.append(vehicle)
            monitored_vehicles = stable_ids.update(monitored_raw, track_now, frame=frame)
            dark = is_low_light(frame)
            night_evidence.update(monitored_vehicles, track_now, low_light=dark)
            # Keep doubtful car boxes visible for diagnosis, but never start
            # a live vehicle session for them merely because YOLO says 'car'.
            verified_vehicles = [d for d in monitored_vehicles if d["night_verified"]]
            vehicles = monitored_vehicles + ignored
            events = tracks.update(verified_vehicles, zones,
                                   config.get("exit_zone", []), track_now)
            for event in events:
                pending_sessions[event["session_id"]] = event
            # 区画占有だけには信頼度が低い検出を使わない
            occupancy_vehicles = [d for d in monitored_vehicles
                                  if d["confidence"] >= float(config.get("confidence", 0.35))]
            parked_ids = {int(track_id) for track_id, entry in tracks.vehicles.items()
                          if entry.phase == "parked"}
            raw = classify_spaces(occupancy_vehicles, blockers, zones,
                                  parked_track_ids=parked_ids)
            departures = [event["space_uid"] for event in events
                          if event["phase"] == "exiting" and event.get("space_uid")]
            if video_mode:
                # Camera-independent recorded-video state machine. Time is
                # derived from the actual source-video frame index, not
                # inference completion, so 5s always means 5s of footage.
                video_seconds = recording.frame_index / recording.fps
                statuses, demo_phases = demo_machine.update(
                    monitored_vehicles, zones, inside, video_seconds
                )
                changed = (statuses != previous_statuses
                           or demo_phases != previous_demo_phases)
                if changed:
                    recording.log_status(statuses, phases=demo_phases)
                previous_demo_phases = demo_phases.copy()
            else:
                statuses = observer.update(raw, now, departures=departures)
                demo_phases = None
                changed = statuses != previous_statuses
                if changed:
                    recording.log_status(statuses)
            # ネットワーク更新が遅くても、推論直後の判定映像を先に保存する。
            phases = {int(tid): record.phase for tid, record in tracks.vehicles.items()}
            for detection in vehicles:
                ident = detection.get("track_id")
                detection["phase"] = phases.get(int(ident), "untracked") if ident is not None else "untracked"
            diagnostic_recorder.write(vehicles, zones, statuses, now)
            annotated = overlay(frame, zones, statuses, vehicles, blockers, phases)
            if video_mode:
                from video_demo_support import draw_demo_phase_labels
                annotated = draw_demo_phase_labels(
                    annotated, cv2, zones, demo_phases
                )
                annotated = draw_demo_watermark(
                    annotated, cv2, recording.frame_index / recording.fps
                )
            visual_recorder.write(annotated, now=time.monotonic())
            should_send = changed or now - last_push >= 5 or (bool(pending_sessions) and now - last_push >= 1)
            if should_send:
                if writer:
                    rows = (demo_status_rows(config, statuses, utc_now(), demo_phases)
                            if video_mode else [{
                        "facility_id": config["facility_id"], "space_uid": uid,
                        "status": status, "confidence": None,
                        "source": "yolo", "checked_at": utc_now(),
                    } for uid, status in statuses.items()])
                    try:
                        writer.upsert("parking_live_status", rows, "facility_id,space_uid")
                        if video_mode and not demo_visible:
                            set_demo_visibility(writer, True)
                            demo_visible = True
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
                cv2.imshow("Recorded video YOLO demo (q to stop)" if video_mode else
                           "Parking camera (q to quit)", view)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        # 再生可能なMP4にするため、停止時には両方のライターを閉じる。
        if visual_recorder is not None:
            visual_recorder.close()
        if diagnostic_recorder is not None:
            diagnostic_recorder.close()
        recording.close()  # 停止・通信断時にも動画とCSVを確定する。
        if writer and video_mode:
            try:
                set_demo_visibility(writer, False)
            except (error.URLError, error.HTTPError, OSError, ValueError) as exc:
                print(f"【重要】録画実演の共有OFFに失敗しました。"
                      f"20秒で古い状態は無効になりますが管理者が公開設定を確認してください: {exc}")
        if camera is not None:
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
