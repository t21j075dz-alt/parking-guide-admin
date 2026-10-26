"""駐車場の車両追跡と区画状態判定。カメラ・ネットワークに依存しない純粋な処理。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

VEHICLES = {"car", "van", "truck", "bus", "motor", "motorcycle"}
OBSTACLES = {
    "traffic cone", "traffic_cone", "cone", "shopping cart", "shopping_cart",
    "trolley", "cart", "barrier", "bollard", "obstacle",
}


def inside(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """画像上の比率座標 (0-1) が多角形に入っているかを判定する。"""
    if len(polygon) < 3:
        return False
    x, y = point
    hit = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi) + xi
        ):
            hit = not hit
        j = i
    return hit


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Detection:
    """YOLOによる検出結果。pointはバウンディングボックス下端中央。"""
    label: str
    point: tuple[float, float]
    confidence: float
    track_id: int | None = None


@dataclass
class Journey:
    """1つのカメラ内で追跡する、匿名の車両セッション。"""
    track_id: int
    entered_at: datetime
    last_seen_at: datetime
    position: tuple[float, float]
    session_id: str = field(default_factory=lambda: str(uuid4()))
    phase: str = "entering"  # entering / moving / parked / exiting / exited / lost
    space_uid: str | None = None
    parked_at: datetime | None = None
    left_space_at: datetime | None = None
    exited_at: datetime | None = None
    candidate_space: str | None = None
    candidate_since: datetime | None = None
    previous_position: tuple[float, float] | None = None
    stationary_since: datetime | None = None
    last_sent_at: datetime | None = None
    last_sent_phase: str | None = None


class ParkingEngine:
    """撮影範囲内の車両イベントと、撮影できる区画の状態を判定する。

    ・駐車状態は数秒間の継続を確認してから確定。
    ・移動中の車両も、区画内にいる間は空き扱いしない。
    ・見失った駐車車両の区画は空きにせず「未確認」。
    ・コーン/カートを学習したモデルがない場合は空き確定を控える。
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.slots: dict[str, list[list[float]]] = config["slots"]
        self.entry_zone = config.get("entry_zone", [])
        self.exit_zone = config.get("exit_zone", [])
        self.dwell = float(config.get("park_confirm_seconds", 8))
        self.lost_after = float(config.get("lost_seconds", 15))
        self.require_obstacles = bool(config.get("require_obstacle_detection", True))
        self.journeys: dict[int, Journey] = {}
        self.unresolved_slots: set[str] = set()
        self.last_car_seen: dict[str, datetime] = {}
        self.last_obstacle_seen: dict[str, datetime] = {}
        self.last_states: dict[str, str] = {}
        self.last_emitted: dict[str, datetime] = {}

    def slot_at(self, point: tuple[float, float]) -> str | None:
        return next((uid for uid, poly in self.slots.items() if inside(point, poly)), None)

    def update(
        self, detections: list[Detection], now: datetime | None = None,
        obstacle_model_ready: bool = False,
    ) -> tuple[list[dict], list[dict]]:
        """(送信すべき区画状態, 送信すべき車両セッション) を返す。"""
        now = now or utc_now()
        touched_slots: set[str] = set()
        obstacles: set[str] = set()
        seen_ids: set[int] = set()
        changed: list[Journey] = []

        for det in detections:
            label = det.label.lower().strip()
            slot = self.slot_at(det.point)
            if label in OBSTACLES:
                if slot:
                    obstacles.add(slot)
                    self.last_obstacle_seen[slot] = now
                continue
            if label not in VEHICLES:
                continue
            if slot:
                touched_slots.add(slot)
                self.last_car_seen[slot] = now
            if det.track_id is None:
                # トラッカーIDがない車も区画占有には数える。
                continue

            seen_ids.add(det.track_id)
            item = self.journeys.get(det.track_id)
            if item is None:
                item = Journey(det.track_id, now, now, det.point)
                self.journeys[det.track_id] = item
                changed.append(item)
            else:
                item.previous_position = item.position
                item.position = det.point
                item.last_seen_at = now

            was_phase = item.phase
            previous_space = item.space_uid
            if item.phase in {"exited", "lost"}:
                continue

            if item.phase == "entering" and (now - item.entered_at).total_seconds() >= 2:
                item.phase = "moving"

            if item.phase == "parked" and slot != item.space_uid:
                # 区画からの移動を実際に検知できたときだけ出庫を確定する。
                item.phase = "exiting"
                item.left_space_at = now
                if previous_space:
                    self.unresolved_slots.discard(previous_space)
            elif item.phase not in {"parked", "exiting"}:
                if slot != item.candidate_space:
                    item.candidate_space = slot
                    item.candidate_since = now if slot else None
                    item.stationary_since = now if slot else None
                elif slot and item.previous_position:
                    distance = sum((a - b) ** 2 for a, b in zip(item.position, item.previous_position)) ** 0.5
                    if distance > float(self.config.get("stationary_shift", 0.015)):
                        item.stationary_since = now

                if (slot and item.candidate_since and item.stationary_since
                    and (now - item.candidate_since).total_seconds() >= self.dwell
                    and (now - item.stationary_since).total_seconds() >= self.dwell):
                    item.phase = "parked"
                    item.space_uid = slot
                    item.parked_at = item.candidate_since
                    self.unresolved_slots.discard(slot)

            if item.phase == "exiting" and self.exit_zone and inside(det.point, self.exit_zone):
                item.phase = "exited"
                item.exited_at = now

            if item.phase != was_phase or item.space_uid != previous_space:
                changed.append(item)

        # 一時遮蔽を考慮し、一定時間見えない場合は見失いとして残す。
        for track_id, item in list(self.journeys.items()):
            if track_id in seen_ids:
                continue
            gap = (now - item.last_seen_at).total_seconds()
            if gap >= self.lost_after and item.phase not in {"lost", "exited"}:
                if item.phase == "parked" and item.space_uid:
                    self.unresolved_slots.add(item.space_uid)
                item.phase = "lost"
                changed.append(item)
            if gap > 3600:
                self.journeys.pop(track_id)

        states = []
        for uid in self.slots:
            # カメラが一時的に物体を見失った間は、決して「空き」にしない。
            car_recent = uid in self.last_car_seen and (
                now - self.last_car_seen[uid]).total_seconds() < self.lost_after
            obstacle_recent = uid in self.last_obstacle_seen and (
                now - self.last_obstacle_seen[uid]).total_seconds() < self.lost_after
            if uid in touched_slots:
                status = "occupied"
            elif uid in obstacles:
                status = "blocked"
            elif (uid in self.unresolved_slots or car_recent or obstacle_recent
                  or (self.require_obstacles and not obstacle_model_ready)):
                status = "unknown"
            else:
                status = "available"

            last = self.last_states.get(uid)
            emitted = self.last_emitted.get(uid)
            if last != status or emitted is None or (now - emitted).total_seconds() >= 5:
                states.append({"space_uid": uid, "status": status, "checked_at": now.isoformat()})
                self.last_states[uid] = status
                self.last_emitted[uid] = now

        # 駐車中も5秒に1度最終確認を記録。再送時は同一セッションIDにupsert。
        out_journeys = []
        for item in self.journeys.values():
            periodic = not item.last_sent_at or (now - item.last_sent_at).total_seconds() >= 5
            if item in changed or (periodic and item.phase not in {"lost", "exited"}):
                out_journeys.append({
                    "session_id": item.session_id,
                    "track_id": item.track_id,
                    "phase": item.phase,
                    "space_uid": item.space_uid,
                    "entered_at": item.entered_at.isoformat(),
                    "parked_at": item.parked_at.isoformat() if item.parked_at else None,
                    "left_space_at": item.left_space_at.isoformat() if item.left_space_at else None,
                    "exited_at": item.exited_at.isoformat() if item.exited_at else None,
                    "last_seen_at": item.last_seen_at.isoformat(),
                    "position_x": round(item.position[0], 5),
                    "position_y": round(item.position[1], 5),
                })
                item.last_sent_at = now
                item.last_sent_phase = item.phase
        return states, out_journeys

    def offline_states(self, now: datetime | None = None) -> list[dict]:
        """カメラ停止時は全区画を未確認にする。"""
        now = now or utc_now()
        return [{"space_uid": uid, "status": "unknown", "checked_at": now.isoformat()}
                for uid in self.slots]
