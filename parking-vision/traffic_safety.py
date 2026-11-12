# -*- coding: utf-8 -*-
"""Fixed-camera crowd alerts; no images, identities or movement tracks are published."""
from __future__ import annotations

from math import isfinite
from time import monotonic


def _bbox_iou(left, right):
    if not left or not right or len(left) != 4 or len(right) != 4:
        return 0.0
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    a = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    b = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return area / max(1e-9, a + b - area)


def _in_poly(point, polygon):
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[(i + 1) % len(polygon)]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _bounds(spaces, entry_zone):
    points = [p for vertices in (spaces or {}).values()
              for p in vertices if len(p) == 2]
    points += [p for p in (entry_zone or []) if len(p) == 2]
    if not points:
        return None
    return (max(0., min(p[0] for p in points) - .13),
            max(0., min(p[1] for p in points) - .13),
            min(1., max(p[0] for p in points) + .13),
            min(1., max(p[1] for p in points) + .13))


class CrowdSafetyMonitor:
    """Stable warnings only after sustained detections inside a monitored area."""

    def __init__(self, *, spaces, entry_zone=None, monitor_zone=None,
                 person_threshold=3, bicycle_threshold=2,
                 confirm_seconds=2., clear_seconds=5., confidence=.5):
        self.monitor_zone = monitor_zone if monitor_zone and len(monitor_zone) >= 3 else None
        self.bounds = _bounds(spaces, entry_zone)
        self.thresholds = {"person": person_threshold, "bicycle": bicycle_threshold}
        self.confirm_seconds = confirm_seconds
        self.clear_seconds = clear_seconds
        self.confidence = confidence
        self.active = {"person": False, "bicycle": False}
        self.above_since = {"person": None, "bicycle": None}
        self.below_since = {"person": None, "bicycle": None}

    def _in_area(self, item):
        point = item.get("point")
        if not point or len(point) != 2 or not all(isfinite(float(v)) for v in point):
            return False
        if self.monitor_zone:
            return _in_poly(point, self.monitor_zone)
        if self.bounds:
            x1, y1, x2, y2 = self.bounds
            return x1 <= point[0] <= x2 and y1 <= point[1] <= y2
        return False

    def _count(self, items, name):
        accepted = []
        for item in items:
            if item.get("name") != name or float(item.get("confidence", 0)) < self.confidence:
                continue
            if not self._in_area(item):
                continue
            if any(_bbox_iou(item.get("bbox"), existing.get("bbox")) > .55
                   for existing in accepted):
                continue
            accepted.append(item)
        return len(accepted)

    def observe(self, vehicles, blockers, *, now=None):
        now = float(monotonic() if now is None else now)
        counts = {"person": self._count(blockers, "person"),
                  "bicycle": self._count(vehicles, "bicycle")}
        for kind, count in counts.items():
            if count >= self.thresholds[kind]:
                self.below_since[kind] = None
                if self.above_since[kind] is None:
                    self.above_since[kind] = now
                if now - self.above_since[kind] >= self.confirm_seconds:
                    self.active[kind] = True
            else:
                self.above_since[kind] = None
                if self.below_since[kind] is None:
                    self.below_since[kind] = now
                if now - self.below_since[kind] >= self.clear_seconds:
                    self.active[kind] = False
        return {
            "pedestrian_count": counts["person"],
            "bicycle_count": counts["bicycle"],
            "pedestrian_warning": self.active["person"],
            "bicycle_warning": self.active["bicycle"],
        }
