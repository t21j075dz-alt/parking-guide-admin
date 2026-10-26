"""カメラ内の一時IDとは別に、駐車区画に車両の滞在IDを固定する。

正解は車の画像でなく物理区画(space_uid)を主キーとして扱う。
YOLOのraw/stable track番号が変化しても同じ枠で駐車し続ける限り
駐車セッションIDは変えない。ただし、入れ替わりが疑われる場合は
確定時刻を誤って延長しない。映像やナンバープレートは保存しない。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import hypot
from uuid import uuid4


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_car(d: dict) -> bool:
    # VisDrone car / van を「四輪」として一括扱い
    return d.get("name") in {"car", "van", "truck", "bus", "vehicle"}


def get_slot_detection(detections: list, uid: str, zones: dict):
    """接地点3点が同一区画にある検出だけを候補にする。"""
    from monitor import space_for
    candidates = []
    for d in detections:
        if not is_car(d):
            continue
        if space_for(d["point"], zones) != uid:
            continue
        touched = {space_for(p, zones) for p in d.get("bottom_points", [d["point"]])}
        if touched != {uid}:
            continue
        candidates.append(d)
    if not candidates:
        return None
    # 1区画に別の車が重なるときは確定しない
    if len(candidates) != 1:
        return None
    return candidates[0]


def color_shape(frame, detection):
    """参考用の大まかな車色と画像上の縦横比。精度保証や個体識別はしない。"""
    bbox = detection.get("bbox")
    if not bbox or len(bbox) != 4:
        return ("不明", None)
    x1, y1, x2, y2 = map(float, bbox)
    ratio = round((x2 - x1)/max(1.0, y2 - y1), 2)
    if frame is None:
        return "不明", ratio
    try:
        import cv2
        import numpy as np
        h, w = frame.shape[:2]
        pad_x, pad_y = .25*(x2-x1), .25*(y2-y1)
        x1, y1 = max(0, int(x1+pad_x)), max(0, int(y1+pad_y))
        x2, y2 = min(w, int(x2-pad_x)), min(h, int(y2-pad_y))
        if x2-x1 < 10 or y2-y1 < 10:
            return "不明", ratio
        crop = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        med_h, med_s, med_v = [float(x) for x in np.median(hsv.reshape(-1, 3), axis=0)]
        if med_v < 55:
            return "黒系", ratio
        if med_s < 42:
            if med_v >= 185:
                return "白系", ratio
            return ("銀・灰系" if med_v >= 85 else "黒・灰系"), ratio
        if med_h < 10 or med_h >= 170:
            return "赤系", ratio
        if med_h < 22:
            return "橙・茶系", ratio
        if med_h < 39:
            return "黄系", ratio
        if med_h < 85:
            return "緑系", ratio
        if med_h < 135:
            return "青系", ratio
        return "紫系", ratio
    except (ImportError, ValueError, TypeError, AttributeError):
        return "不明", ratio


@dataclass
class SlotStay:
    uid: str
    camera_number: int
    session_id: str
    first_seen_video: float
    first_seen_wall: str | None
    last_seen_video: float
    last_seen_wall: str
    parked_confirmed_video: float
    park_start_video: float | None
    park_start_wall: str | None
    entered_observed: bool
    color: str
    aspect: float | None
    point: tuple[float, float]
    in_view: bool = True
    visibility: str = "visible"
    phase: str = "parked"
    finished: bool = False

    def row(self, facility_id, camera_id) -> dict:
        return {
            "session_id": self.session_id,
            "facility_id": facility_id, "camera_id": camera_id,
            "track_id": self.camera_number, "phase": self.phase if self.in_view else "lost",
            "space_uid": self.uid,
            "entered_at": self.first_seen_wall or stamp(),
            "parked_at": self.park_start_wall,
            "left_space_at": None, "exited_at": None,
            "last_seen_at": self.last_seen_wall,
            "position_x": self.point[0], "position_y": self.point[1],
        }


class SlotStayManager:
    """IDは停止確定で一度だけ発行。生YOLO IDの変更ではセッションを分割しない。"""

    def __init__(self, facility_id: str, camera_id: str, zones: dict,
                 park_seconds: float = 5.0, confirmed_initially_empty=(),
                 blind_uids=(), occlusion_dependencies=None):
        self.facility_id = facility_id
        self.camera_id = camera_id
        self.zones = zones
        self.park_seconds = park_seconds
        self.confirmed_empty = set(confirmed_initially_empty)
        self.blind_uids = set(blind_uids)
        self.occlusion_dependencies = occlusion_dependencies or {}
        self.next_id = 1_000_000
        self.active: dict[str, SlotStay] = {}
        self.candidates = {}
        self.finished = []
        self.events = []
        self.first_update = True
        self.initial_presence = set()
        self.prev_clear = set(self.confirmed_empty)

    def update(self, detections: list, states: dict, now: float,
               frame=None, departures=()) -> list[dict]:
        events = []
        raw = {
            uid: get_slot_detection(detections, uid, self.zones)
            for uid in self.zones
        }
        if self.first_update:
            self.initial_presence = {uid for uid, d in raw.items() if d is not None}
            self.first_update = False

        # カメラの死角は目視で設定。死角でも車が実際に検出されれば駐車確定可能。
        occluded = set(self.blind_uids)
        for uid, blockers in self.occlusion_dependencies.items():
            if any(states.get(front) == "occupied" for front in blockers):
                occluded.add(uid)

        for uid, det in raw.items():
            state = states.get(uid, "unknown")
            stay = self.active.get(uid)
            if state == "available" and det is None and uid not in occluded:
                self.prev_clear.add(uid)
            if det is None:
                self.candidates.pop(uid, None)
                if stay:
                    stay.in_view = False
                    stay.visibility = "occluded" if uid in occluded else "lost"
                    # 画角外への消失を出庫と誤認しない。明確な出庫後のみ完了する。
                    if uid in departures and state == "available" and uid not in occluded:
                        stay.phase = "exiting"
                        stay.finished = True
                        self.finished.append(stay)
                        events.append({"event": "departure", "uid": uid,
                                       "session_id": stay.session_id,
                                       "time": now, "record": stay})
                        del self.active[uid]
                continue

            point = tuple(det["point"])
            if stay:
                stay.in_view = True
                stay.visibility = "visible"
                stay.last_seen_video = now
                stay.last_seen_wall = stamp()
                stay.point = point
                self.candidates.pop(uid, None)
                continue

            # 初期フレームにいた車の開始時刻は不明。空き確認後に
            # 新しく侵入した車だけ駐車開始時刻を測定する。
            pending = self.candidates.get(uid)
            if pending is None:
                self.candidates[uid] = {
                    "start": now, "latest": now, "point": point,
                    "confirmed_empty": uid in self.prev_clear and uid not in self.initial_presence,
                    "color": color_shape(frame, det)[0],
                    "aspect": color_shape(frame, det)[1],
                    "wall": stamp(),
                }
                continue
            distance = hypot(point[0]-pending["point"][0], point[1]-pending["point"][1])
            # 停止候補は位置がほぼ不変。移動している車は確定しない。
            if distance > .018 or now - pending["latest"] > 1.2:
                self.candidates[uid] = {
                    "start": now, "latest": now, "point": point,
                    "confirmed_empty": pending["confirmed_empty"],
                    "color": color_shape(frame, det)[0],
                    "aspect": color_shape(frame, det)[1],
                    "wall": stamp(),
                }
                continue
            pending["latest"] = now
            if now - pending["start"] < self.park_seconds:
                continue

            observed = pending["confirmed_empty"]
            stay = SlotStay(
                uid=uid,
                camera_number=self.next_id,
                session_id=str(uuid4()),
                first_seen_video=pending["start"],
                first_seen_wall=pending["wall"],
                last_seen_video=now,
                last_seen_wall=stamp(),
                parked_confirmed_video=now,
                park_start_video=pending["start"] if observed else None,
                park_start_wall=pending["wall"] if observed else None,
                entered_observed=observed,
                color=pending["color"], aspect=pending["aspect"],
                point=point,
            )
            self.next_id += 1
            self.active[uid] = stay
            self.prev_clear.discard(uid)
            self.candidates.pop(uid, None)
            events.append({"event": "parked", "uid": uid,
                           "session_id": stay.session_id,
                           "time": now, "record": stay})
        self.events.extend(events)
        return events

    def active_rows(self):
        return [s.row(self.facility_id, self.camera_id) for s in self.active.values()]

    def current_display(self, now):
        return [{
            "space_uid": s.uid,
            "vehicle_id": s.camera_number,
            "session_id": s.session_id,
            "phase": s.phase,
            "visibility": s.visibility,
            "color_estimate": s.color,
            "bounding_box_aspect": s.aspect,
            "duration_seconds": round(max(0, now - s.park_start_video), 2)
            if s.park_start_video is not None else None,
            "started_at_observed": s.entered_observed,
        } for s in self.active.values()]
