#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""駐車場カメラ → YOLO → 車両追跡 → Supabase。

使い方: python monitor.py --config config.json --preview
※ カメラの画像はクラウドに送らず、区画の状態と匿名の追跡情報だけを送ります。
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

from stable_ids import StableIdMatcher
from slot_stays import SlotStayManager
from admin_layout import verify as verify_admin_layout, read_export as read_admin_layout_export

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
    zones = content.get("space_zones") or {}
    if not zones:
        raise ValueError("駐車枠の撮影範囲が未登録です。先に calibrate.py を実行してください")
    for uid, polygon in zones.items():
        if not valid_polygon(polygon):
            raise ValueError(f"{uid} の四隅座標が正しくありません")
    for name in ("entry_zone", "exit_zone"):
        if content.get(name) and not valid_polygon(content[name]):
            raise ValueError(f"{name} の範囲が正しくありません")
    monitored_site = content.get("monitored_site_polygon", [])
    if monitored_site and not valid_polygon(monitored_site):
        raise ValueError("monitored_site_polygon は画像内の正規化した3点以上の敷地境界にしてください")
    blind = content.get("camera_blind_space_uids", [])
    if not isinstance(blind, list) or any(uid not in zones for uid in blind):
        raise ValueError("camera_blind_space_uids に登録していない区画があります")
    occluded_by = content.get("occluded_by_spaces", {})
    if not isinstance(occluded_by, dict) or any(
        uid not in zones or not isinstance(fronts, list) or any(front not in zones or front == uid for front in fronts)
        for uid, fronts in occluded_by.items()
    ):
        raise ValueError("occluded_by_spaces は登録済み区画UIDの対応を指定してください")
    if content.get("admin_layout_export"):
        metadata = read_admin_layout_export(
            content["admin_layout_export"], content["facility_id"], zones
        )
        print("管理アプリの登録済み区画と一致:", len(metadata), "区画")
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
            uid = space_for(point, zones)
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
                 absence_hold_seconds=8.0, initially_confirmed_empty_uids=()):
        self.states = {uid: "unknown" for uid in space_uids}
        self.candidates = {}
        self.since = {}
        self.frames = defaultdict(int)
        self.allow_initial_empty = bool(allow_initial_empty)
        self.initial_approved = set(initially_confirmed_empty_uids)
        self.absence_hold_seconds = float(absence_hold_seconds)
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
            elif reported not in {"blocked", "unknown"}:
                desired = "unknown"

            if desired != self.candidates.get(uid):
                self.candidates[uid] = desired
                self.since[uid] = now
                self.frames[uid] = 1
            else:
                self.frames[uid] += 1
            min_seconds = (5.0 if desired == "available"
                           else 0.3 if desired in {"occupied", "blocked"}
                           else 0.3)
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

    def fetch_layout(self, facility_id: str):
        """本人の管理者ログインを用いて管理レイアウトUIDを確認する。"""
        self._ensure_token()
        query = parse.urlencode({
            "facility_id": "eq." + facility_id,
            "select": "facility_id,layout_data", "limit": 1,
        })
        req = request.Request(
            self.url + "/rest/v1/parking_layouts?" + query,
            headers={
                "apikey": self.key,
                "Authorization": "Bearer " + self.access_token,
            },
            method="GET",
        )
        with request.urlopen(req, timeout=10) as response:
            rows = json.loads(response.read())
        if not rows:
            raise ValueError("管理アプリに登録された施設レイアウトが見つかりません")
        return rows[0]["layout_data"]

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



def classify_spaces(vehicles: list[dict], blockers: list[dict], zones: dict) -> dict[str, str]:
    """接地点を優先。区画境界にかかる曖昧な車は空きとして案内しない。"""
    occupied, blocked, uncertain = set(), set(), set()

    def put(detection, definite):
        center_uid = space_for(detection["point"], zones)
        points = detection.get("bottom_points") or [detection["point"]]
        touched = {space_for(p, zones) for p in points}
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
        put(vehicle, occupied)
    for blocker in blockers:
        put(blocker, blocked)
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
    # 追跡器には低確信度の検出も渡すが、占有判定には最低限の信頼を求める。
    # IDの連続性向上のため、検出した車両そのものはここでは除外しない。
    blockers = [d for d in detector_boxes(results[0], width, height, BLOCKING_NAMES)
                if d["confidence"] >= occupancy_confidence]
    if obstacle_model:
        results_extra = obstacle_model.predict(frame, conf=confidence, verbose=False)
        blockers.extend(detector_boxes(results_extra[0], width, height, BLOCKING_NAMES))
    return vehicles, blockers


def overlay(frame, zones, statuses, vehicle_detections, obstacles):
    import cv2
    h, w = frame.shape[:2]
    for uid, poly in zones.items():
        points = [(int(x * w), int(y * h)) for x, y in poly]
        for first, second in zip(points, points[1:] + points[:1]):
            cv2.line(frame, first, second, (0, 200, 255), 2)
        status = statuses.get(uid, "unknown")
        cv2.putText(frame, f"{uid}: {status}", points[0],
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (250, 255, 255), 2)
    for d in vehicle_detections + obstacles:
        px, py = d["point"]
        label = f"{d['name']} ID{d['track_id']}" if d["track_id"] is not None else d["name"]
        cv2.putText(frame, label, (int(px * w), int(py * h)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 255, 20), 2)


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
    if isinstance(source, str) and source.isdecimal():
        source = int(source)
    camera = cv2.VideoCapture(source)
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
    if writer and config.get("verify_admin_layout_on_cloud", True):
        # クラウドへ誤った施設/区画IDを公開しないために必ず事前照合する。
        metadata = verify_admin_layout(
            writer.fetch_layout(config["facility_id"]), config["facility_id"], zones
        )
        print("管理アプリの登録枠と照合成功:", len(metadata), "区画")
    stay_manager = SlotStayManager(
        config["facility_id"], config["camera_id"], zones,
        park_seconds=float(config.get("park_seconds", 5)),
        confirmed_initially_empty=config.get("initially_confirmed_empty_uids", []),
        blind_uids=config.get("camera_blind_space_uids", []),
        occlusion_dependencies=config.get("occluded_by_spaces", {}),
    )
    observer = SpaceObserver(
        zones,
        allow_initial_empty=bool(config.get("allow_unverified_initial_empty", False)),
        absence_hold_seconds=float(config.get("occupied_hold_seconds", 8)),
        initially_confirmed_empty_uids=config.get("initially_confirmed_empty_uids", []),
    )
    tracks = VehicleTracker(config["facility_id"], config["camera_id"],
                            float(config.get("park_seconds", 5)),
                            lost_seconds=float(config.get("reid_window_seconds", 12)))
    stable_ids = StableIdMatcher(max_missing=float(config.get("reid_window_seconds", 12)))
    last_push, last_print = 0., 0.
    previous_statuses = None
    pending_sessions = {}  # 駐車区画の固定セッションだけを管理アプリへ送信する
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("映像を取得できません。更新停止後、利用者画面では自動的に未確認になります。")
                break
            vehicles, blockers = infer_frame(
                vehicle_model, obstacle_model, frame,
                float(config.get("tracking_confidence", 0.15)),
                tracker_file=str(config.get("tracker_file", DEFAULT_TRACKER)),
                image_size=int(config.get("image_size", 960)),
                occupancy_confidence=float(config.get("confidence", 0.35)),
            )
            now = time.monotonic()
            # 登録済み敷地外の車を追跡対象から除外する。背景道路の車はカウントしない。
            site = config.get("monitored_site_polygon") or []
            if site:
                vehicles = [d for d in vehicles if inside(d["point"], site)]
                blockers = [d for d in blockers if inside(d["point"], site)]
            vehicles = stable_ids.update(vehicles, now, frame=frame)
            events = tracks.update(vehicles, zones, config.get("exit_zone", []), now)
            for event in events:
                pending_sessions[event["session_id"]] = event
            # 区画占有だけには信頼度が低い検出を使わない
            occupancy_vehicles = [d for d in vehicles
                                  if d["confidence"] >= float(config.get("confidence", 0.35))]
            raw = classify_spaces(occupancy_vehicles, blockers, zones)
            departures = [event["space_uid"] for event in events
                          if event["phase"] == "exiting" and event.get("space_uid")]
            statuses = observer.update(raw, now, departures=departures)
            # 管理アプリで設定された視野の死角は、車を検出できた場合を除き空き扱いしない。
            blind = set(config.get("camera_blind_space_uids", []))
            for uid, fronts in config.get("occluded_by_spaces", {}).items():
                if any(statuses.get(front) == "occupied" for front in fronts):
                    blind.add(uid)
            for uid in blind:
                if raw.get(uid) != "occupied":
                    statuses[uid] = "unknown"

            # 生IDに依存しない、「駐車枠に固定した駐車セッション」を発行。
            stay_events = stay_manager.update(
                occupancy_vehicles, statuses, now,
                frame=frame, departures=departures,
            )
            for event in stay_events:
                pending_sessions[event["session_id"]] = event["record"].row(
                    config["facility_id"], config["camera_id"]
                )
            changed = statuses != previous_statuses
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
                        # 生IDが頻繁に変化する移動車両はクラウドへ送らない。
                        # 1駐車枠につき1つの滞在IDを持つ固定セッションだけ送信。
                        session_rows = {
                            row["session_id"]: row for row in stay_manager.active_rows()
                        }
                        session_rows.update(pending_sessions)
                        writer.upsert(
                            "parking_vehicle_sessions", list(session_rows.values()),
                            "session_id",
                        )
                        pending_sessions.clear()
                    except (error.URLError, error.HTTPError, OSError, KeyError) as exc:
                        print(f"クラウド共有に失敗: {exc}（認証・権限・通信をご確認ください）")
                if changed or now - last_print >= 5:
                    print(" / ".join(f"{uid}={STATUS_NAMES[status]}" for uid, status in statuses.items()))
                    last_print = now
                if not writer:
                    pending_sessions.clear()
                previous_statuses, last_push = statuses.copy(), now
            if args.preview:
                overlay(frame, zones, statuses, vehicles, blockers)
                cv2.imshow("Parking camera (q to quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        if args.preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except error.HTTPError as exc:
        sys.exit(f"クラウド認証・保存に失敗しました（HTTP {exc.code}）。ログインと権限を確認してください")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.exit(f"設定を確認してください: {exc}")
