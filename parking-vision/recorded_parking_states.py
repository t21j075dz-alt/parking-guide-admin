# -*- coding: utf-8 -*-
"""録画動画の車体底面で6区画を判定する、独立した状態遷移。

初期: 空き (録画実演だけ)
車底面が枠内に5秒以上:
  動いている → 駐車中（入庫動作）
  5秒以上動いていない → 停車中
停車中の同一車両が移動し、車底面が枠外 → 出庫中
車底面が継続して枠外 → 空き

誤判定防止:
- YOLOボックスの『下側だけ』から接地領域を推定し、車体全体で
  隣接区画を占有させない。タイヤキーポイントとは呼ばない。
- 5秒は動画の経過時間。読み飛ばしフレームを5秒の証拠として
  加算しない。2.5秒を超える観測断絶は連続判定をやり直す。
- ID消失だけでは出庫としない。追跡された車の区画外移動が必要。
- 重なり候補が同程度のときは『未確認』にし、隣の区画を駐車中にしない。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot

VALID_PHASES = ("available", "parking_in", "stopped", "exiting", "unknown")
DISPLAY_PHASES = {
    "available": "空き",
    "parking_in": "駐車中",
    "stopped": "停車中",
    "exiting": "出庫中",
    "unknown": "確認中",
}
# The user-facing app already interprets occupied as not available.
STATUS_FOR_PHASE = {
    "available": "available",
    "parking_in": "occupied",
    "stopped": "occupied",
    "exiting": "occupied",
    "unknown": "unknown",
}
ENTRY_SECONDS = 5.0
STOP_SECONDS = 5.0
LEAVE_SECONDS = 1.5
MAX_GAP_SECONDS = 2.5
TRACK_HISTORY_SECONDS = 6.2


def bottom_footprint_candidate(detection, zones, inside):
    """Return (one stall or None, touched stalls, normalized bottom-center).

    This is an image-derived bottom-contact *approximation* across the
    bottom 10% of the box, not a physically measured car underbody.
    """
    box = detection.get("bbox")
    size = detection.get("image_size")
    if not box or len(box) != 4 or not size or min(size) <= 0:
        return None, set(), None
    width, height = size
    x1, y1, x2, y2 = map(float, box)
    if x2 - x1 < 10 or y2 - y1 < 10:
        return None, set(), None
    counts = {uid: 0 for uid in zones}
    for yf in (.92, .965, .995):
        for xf in (.10, .20, .30, .40, .50, .60, .70, .80, .90):
            point = ((x1 + (x2 - x1) * xf) / width,
                     (y1 + (y2 - y1) * yf) / height)
            hits = [uid for uid, polygon in zones.items() if inside(point, polygon)]
            if len(hits) == 1:
                counts[hits[0]] += 1
    ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    uid, count = ranked[0] if ranked else (None, 0)
    second = ranked[1][1] if len(ranked) > 1 else 0
    total = sum(counts.values())
    touched = {uid for uid, score in counts.items() if score >= 3}
    # Example: 14:11 for two adjacent spaces => strongest one wins.
    # A true 12:12 split remains ambiguous: UNKNOWN, not a false neighbor.
    winner = (
        uid if uid and count >= 5 and count >= total * .60
        and count >= second * 1.35 else None
    )
    anchor = ((x1 + x2) / (2 * width),
              (y1 + (y2 - y1) * .96) / height)
    if winner is None and total >= 12:
        # A car parked diagonally can cover exactly half of two polygons
        # with its rectangular YOLO bbox. This is common in the user's
        # 3rd/4th-space footage (13/13 samples for several minutes).
        # Use the bottom-center proximity to the actual calibrated stalls
        # ONLY when one polygon is substantially nearer. Do not force
        # a win for a symmetric vehicle or a box far from either stall.
        contenders = [(uid, n) for uid, n in ranked[:2] if n >= 6]
        if len(contenders) == 2:
            distances = []
            for zone_uid, n in contenders:
                corners = zones[zone_uid]
                centroid = (
                    sum(float(p[0]) for p in corners) / len(corners),
                    sum(float(p[1]) for p in corners) / len(corners),
                )
                dist = hypot(
                    anchor[0] - centroid[0], anchor[1] - centroid[1]
                )
                distances.append((dist, zone_uid, n))
            distances.sort()
            nearest, zone_uid, n = distances[0]
            runner_up = distances[1][0]
            if (nearest <= .075 and runner_up > 0
                    and nearest <= runner_up * .64
                    and n >= total * .30):
                winner = zone_uid
    return winner, touched, anchor


@dataclass
class TrackHistory:
    samples: deque = field(default_factory=deque)
    last_seen: float = -1.0

    def update(self, clock, position):
        if self.last_seen >= 0 and clock - self.last_seen > MAX_GAP_SECONDS:
            self.samples.clear()
        self.last_seen = clock
        self.samples.append((clock, position))
        while self.samples and clock - self.samples[0][0] > TRACK_HISTORY_SECONDS:
            self.samples.popleft()

    def is_stopped(self, clock):
        if len(self.samples) < 3:
            return False
        last = self.samples[-1][1]
        oldest = next(((t, p) for t, p in self.samples
                       if clock - t >= STOP_SECONDS), None)
        if oldest is None:
            return False
        recent = [(t, p) for t, p in self.samples if clock - t <= STOP_SECONDS + .35]
        xs = sorted(p[0] for _, p in recent)
        ys = sorted(p[1] for _, p in recent)
        center = xs[len(xs)//2], ys[len(ys)//2]
        return (hypot(last[0]-oldest[1][0], last[1]-oldest[1][1]) <= .016
                and sum(hypot(p[0]-center[0], p[1]-center[1]) <= .017
                        for _, p in recent) >= .85 * len(recent))

    def is_moving(self, clock):
        # Very slow reversing/parking is often <2% of the frame per 2s.
        # Inspect both short motion (rapid exit) and 5s cumulative drift.
        for window, minimum in ((2.6, .018), (5.2, .025)):
            samples = [(t, p) for t, p in self.samples if clock - t <= window]
            if len(samples) < 2 or samples[-1][0] - samples[0][0] < .4:
                continue
            first, last = samples[0][1], samples[-1][1]
            if hypot(last[0]-first[0], last[1]-first[1]) >= minimum:
                return True
        return False


@dataclass
class StallProgress:
    phase: str = "available"
    track_id: int | None = None
    overlap_started: float | None = None
    last_inside: float | None = None
    missing_started: float | None = None
    outside_started: float | None = None
    movement_observed: bool = False
    last_change: float = 0.0

    def set_phase(self, phase, now):
        if self.phase == phase:
            return
        self.phase = phase
        self.last_change = now


class RecordedParkingStateMachine:
    """Video-only state machine. Output statuses fit existing guide API."""

    def __init__(self, space_uids):
        self.stalls = {uid: StallProgress() for uid in space_uids}
        self.tracks = {}
        self.last_clock = -1.
        self.events = []

    def update(self, detections, zones, inside, now):
        now = float(now)
        if now < self.last_clock:
            raise ValueError("録画時刻が逆行しました。再生の最初からやり直してください")
        self.last_clock = now
        observations = {}
        tracked_all = {}
        ambiguous = set()

        for detection in detections:
            if (detection.get("monitored") is False
                    or detection.get("night_verified") is False
                    or detection.get("confidence", 0) < .35):
                # An unverified car-like object cannot confirm a stall.
                continue
            tid = detection.get("track_id")
            if tid is None:
                continue
            tid = int(tid)
            uid, touched, anchor = bottom_footprint_candidate(
                detection, zones, inside
            )
            if anchor is None:
                continue
            history = self.tracks.setdefault(tid, TrackHistory())
            history.update(now, anchor)
            tracked_all[tid] = {"zone": uid, "anchor": anchor,
                                "moving": history.is_moving(now),
                                "stopped": history.is_stopped(now),
                                "touched": touched,
                                "confidence": detection["confidence"]}
            if uid is not None:
                old = observations.get(uid)
                if old is None or old["confidence"] < detection["confidence"]:
                    observations[uid] = {**tracked_all[tid], "tid": tid}
            else:
                ambiguous.update(touched)
            detection["demo_zone"] = uid
            detection["demo_moving"] = tracked_all[tid]["moving"]
            detection["demo_stopped"] = tracked_all[tid]["stopped"]

        # Prevent unbounded track accumulation over multi-hour videos.
        for tid in list(self.tracks):
            if now - self.tracks[tid].last_seen > 20:
                del self.tracks[tid]

        for uid, stall in self.stalls.items():
            observation = observations.get(uid)
            if stall.phase == "available":
                if observation is not None:
                    tid = observation["tid"]
                    reset_overlap = (stall.track_id != tid or stall.last_inside is None
                                     or now - stall.last_inside > MAX_GAP_SECONDS)
                    if reset_overlap:
                        stall.overlap_started = now
                        stall.movement_observed = False
                    stall.track_id = tid
                    stall.last_inside = now
                    stall.missing_started = None
                    stall.movement_observed |= observation["moving"]
                    if observation["stopped"] and now - stall.overlap_started >= ENTRY_SECONDS:
                        stall.set_phase("stopped", now)
                    elif (now - stall.overlap_started >= ENTRY_SECONDS
                          and stall.movement_observed):
                        # A moving vehicle spent at least five observed seconds
                        # with its underside above this parking polygon.
                        stall.set_phase("parking_in", now)
                else:
                    if stall.last_inside is not None and now - stall.last_inside > MAX_GAP_SECONDS:
                        stall.track_id = None
                        stall.overlap_started = None
                        stall.last_inside = None
                        stall.movement_observed = False
            elif stall.phase in ("parking_in", "stopped"):
                own = tracked_all.get(stall.track_id)
                if own and own["zone"] == uid:
                    stall.last_inside = now
                    stall.outside_started = None
                    if stall.phase == "parking_in" and own["stopped"]:
                        stall.set_phase("stopped", now)
                elif (own and own["zone"] != uid and own["moving"]
                      and uid not in own["touched"]):
                    if stall.outside_started is None:
                        stall.outside_started = now
                    if stall.phase == "stopped":
                        # The user's exit definition is a stationary car
                        # *starting to move* with its lower edge no longer
                        # inside the stall. Register EXITING immediately
                        # after positive tracked motion out. A momentary
                        # bbox wobble returning inside will be rolled back
                        # below; no 0.5s blind delay until the ID vanishes.
                        stall.set_phase("exiting", now)
                    elif now - stall.outside_started >= LEAVE_SECONDS:
                        # Aborted parking manoeuvre (never stopped).
                        # Only a previously stopped car enters EXITING.
                        stall.set_phase("available", now)
                        stall.track_id = None
                        stall.overlap_started = None
                        stall.last_inside = None
                        stall.movement_observed = False
                else:
                    # Lost detections are not evidence that a car departed.
                    stall.outside_started = None
            else:  # exiting: only reached after observed tracked movement out.
                own = tracked_all.get(stall.track_id)
                if own and own["zone"] == uid:
                    # A temporary geometry wobble: the tracked car is back.
                    stall.outside_started = None
                    stall.set_phase("stopped", now)
                elif observation is not None:
                    # Another car is in the stall; clearing it would be unsafe.
                    stall.outside_started = None
                    stall.set_phase("stopped", now)
                elif stall.outside_started is not None and (
                        (own and own["moving"]) or own is None):
                    # A proven departure can complete even after the car
                    # passes beyond the configured camera monitoring region.
                    # Mere disappearance from STOPPED never reaches here.
                    if now - stall.outside_started >= LEAVE_SECONDS:
                        stall.set_phase("available", now)
                        stall.track_id = None
                        stall.overlap_started = None
                        stall.last_inside = None
                        stall.movement_observed = False
                # Without prior movement *out*, a lost track alone is never free.

        # a transition-free available stall remains AVAILABLE. A physically
        # visible but unconfirmed car is reported UNKNOWN until 5s.
        phases = {}
        for uid, stall in self.stalls.items():
            # Internal "available" while a body is being assessed is exposed
            # as UNKNOWN, so the map and DB do not contradict each other.
            phases[uid] = (
                "unknown"
                if stall.phase == "available" and (
                    stall.last_inside is not None or uid in ambiguous
                )
                else stall.phase
            )
        statuses = {uid: STATUS_FOR_PHASE[phase] for uid, phase in phases.items()}
        return statuses, phases
