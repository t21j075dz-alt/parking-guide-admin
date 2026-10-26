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
                    self.parked_at = self.candidate_started_at or utc_now()
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
    def __init__(self, facility_id: str, camera_id: str, park_seconds: float = 5):
        self.facility_id, self.camera_id = facility_id, camera_id
        self.park_seconds = park_seconds
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
            elif now - entry.seen_monotonic > 3:
                entry.phase = "lost"  # IDが消えたことを「退出」とは決めつけない
                changed.append(entry.row())
                del self.vehicles[track_id]
        return changed


class SpaceObserver:
    """2フレーム連続で占有確認。空きは5秒連続確認後にだけ確定する。"""
    def __init__(self, space_uids):
        self.states = {uid: "unknown" for uid in space_uids}
        self.candidates = {}
        self.since = {}
        self.frames = defaultdict(int)

    def update(self, raw: dict[str, str], now: float) -> dict[str, str]:
        for uid, desired in raw.items():
            if desired != self.candidates.get(uid):
                self.candidates[uid] = desired
                self.since[uid] = now
                self.frames[uid] = 1
            else:
                self.frames[uid] += 1
            min_seconds = 5.0 if desired == "available" else 0.3
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
        output.append({"name": name, "point": point, "track_id": track_id,
                       "confidence": float(score), "bbox": bbox})
    return output



def classify_spaces(vehicles: list[dict], blockers: list[dict], zones: dict) -> dict[str, str]:
    """同じ判定規則をライブ・録画テストで共有する。車両が最優先、次に障害物。"""
    occupied = {space_for(d["point"], zones) for d in vehicles}
    blocked = {space_for(d["point"], zones) for d in blockers}
    return {
        uid: "occupied" if uid in occupied else "blocked" if uid in blocked
        else "available" for uid in zones
    }


def infer_frame(vehicle_model, obstacle_model, frame, confidence: float):
    """モデルが使えるか確認しながら1フレームを判定する。車両IDはByteTrackで取得する。"""
    height, width = frame.shape[:2]
    results = vehicle_model.track(
        frame, persist=True, tracker="bytetrack.yaml", conf=confidence, verbose=False,
    )
    vehicles = detector_boxes(results[0], width, height, VEHICLE_NAMES)
    blockers = detector_boxes(results[0], width, height, BLOCKING_NAMES)
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
    observer = SpaceObserver(zones)
    tracks = VehicleTracker(config["facility_id"], config["camera_id"],
                            float(config.get("park_seconds", 5)))
    stable_ids = StableIdMatcher(max_missing=float(config.get("reid_window_seconds", 12)))
    last_push, last_print = 0., 0.
    previous_statuses = None
    pending_sessions = {}  # 出口通過・追跡消失など、画面から消える直前のイベントも保存する
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("映像を取得できません。更新停止後、利用者画面では自動的に未確認になります。")
                break
            vehicles, blockers = infer_frame(
                vehicle_model, obstacle_model, frame, float(config.get("confidence", 0.35)),
            )
            now = time.monotonic()
            vehicles = stable_ids.update(vehicles, now, frame=frame)
            for event in tracks.update(vehicles, zones, config.get("exit_zone", []), now):
                pending_sessions[event["session_id"]] = event
            raw = classify_spaces(vehicles, blockers, zones)
            statuses = observer.update(raw, now)
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
