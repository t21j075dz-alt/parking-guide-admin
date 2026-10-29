# -*- coding: utf-8 -*-
"""Avoid claiming stationary night-time objects are real cars.

In near-dark scenes YOLO may confidently label a guardrail, vegetation or
headlight reflection as 'car'. Confidence and a stable box are NOT evidence
of a real vehicle. Require a *continuous observed approach* before this
object is allowed into parking tracking. This cannot identify vehicles
parked before the camera started; those remain unverified, not empty.
"""
from __future__ import annotations

from collections import deque
from math import hypot
from statistics import median


class NightVehicleEvidenceGate:
    def __init__(self, min_displacement=.055, lifetime_seconds=12.):
        self.min_displacement = float(min_displacement)
        self.lifetime_seconds = float(lifetime_seconds)
        self.history = {}
        self.verified = set()
        self.last_seen = {}

    @staticmethod
    def _stable_center(samples):
        return (median(p[0] for p in samples),
                median(p[1] for p in samples))

    def _observed_approach(self, observations):
        if len(observations) < 7:
            return False
        ordered = list(observations)
        first = ordered[:3]
        last = ordered[-3:]
        if last[-1][0] - first[0][0] < 1.8:
            return False
        start = self._stable_center([p for _, p in first])
        end = self._stable_center([p for _, p in last])
        dx, dy = end[0] - start[0], end[1] - start[1]
        net = hypot(dx, dy)
        if net < self.min_displacement:
            return False
        # Reject single-frame location jumps and noisy dark 'car' boxes:
        # several consecutive steps must move along the same direction.
        ux, uy = dx / net, dy / net
        advances = []
        for (_, a), (_, b) in zip(ordered, ordered[1:]):
            projection = (b[0] - a[0]) * ux + (b[1] - a[1]) * uy
            advances.append(projection)
        meaningful = sum(value >= .007 for value in advances)
        return meaningful >= 3 and max(advances) < .055

    def update(self, detections, now, low_light):
        # Discard memory of stale tracks: a new object must not inherit
        # previous night evidence after ID retirement/reuse.
        for ident, stamp in list(self.last_seen.items()):
            if now - stamp > self.lifetime_seconds:
                self.last_seen.pop(ident, None)
                self.history.pop(ident, None)
                self.verified.discard(ident)
        for det in detections:
            raw_id = det.get("track_id")
            if raw_id is None:
                det["night_verified"] = not low_light
                det["night_verification_reason"] = "NO_STABLE_ID" if low_light else "DAY"
                continue
            ident = int(raw_id)
            self.last_seen[ident] = float(now)
            records = self.history.setdefault(ident, deque(maxlen=100))
            records.append((float(now), tuple(det["point"])))
            while records and now - records[0][0] > 9:
                records.popleft()
            if not low_light:
                # Daylight provides much more usable visual detail.
                self.verified.add(ident)
            elif ident not in self.verified and self._observed_approach(records):
                self.verified.add(ident)
            det["night_verified"] = ident in self.verified
            det["night_verification_reason"] = (
                "TRACKED_APPROACH" if ident in self.verified
                else "NO_OBSERVED_VEHICLE_APPROACH")
        return detections
