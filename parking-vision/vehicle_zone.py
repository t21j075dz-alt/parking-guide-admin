# -*- coding: utf-8 -*-
"""Fixed-camera approximate parking-zone mapping.

A reliable pair of image-derived tyre contacts is preferred. When tyre
detection fails, count sample points in the vehicle's lower silhouette
instead of pretending the bottom of the YOLO box is a tyre position.
This module estimates a candidate *zone*, not that the vehicle is parked.
A separate stable-track stationary check is mandatory for OCCUPIED.
"""
from __future__ import annotations


def _unique_zone(point, zones, inside):
    matched = [uid for uid, poly in zones.items() if inside(point, poly)]
    return matched[0] if len(matched) == 1 else None


def locate_vehicle_zone(detection, zones, inside):
    """Return (zone candidate, potentially touched zones, evidence basis)."""
    wheels = detection.get("wheel_points") or []
    wheel_hits = [_unique_zone(p, zones, inside) for p in wheels]
    wheel_uid = (wheel_hits[0] if len(wheels) == 2
                 and wheel_hits[0] is not None
                 and wheel_hits[0] == wheel_hits[1] else None)
    size = detection.get("image_size")
    box = detection.get("bbox")
    counts = {uid: 0 for uid in zones}
    if size and box and len(box) == 4 and size[0] > 0 and size[1] > 0:
        w, h = size
        x1, y1, x2, y2 = [float(v) for v in box]
        if x2 > x1 + 8 and y2 > y1 + 8:
            for yf in (0.67, 0.77, 0.87, 0.93):
                for xf in (0.18, 0.31, 0.44, 0.57, 0.70, 0.82):
                    point = ((x1 + (x2 - x1) * xf) / w,
                             (y1 + (y2 - y1) * yf) / h)
                    uid = _unique_zone(point, zones, inside)
                    if uid:
                        counts[uid] += 1
    ranked = sorted(counts.items(), key=lambda entry: entry[1], reverse=True)
    best_uid, best_count = ranked[0] if ranked else (None, 0)
    runner = ranked[1][1] if len(ranked) > 1 else 0
    total = sum(counts.values())
    # Strong majority. Never choose when the lower body straddles spaces.
    body_uid = (best_uid if best_count >= 7 and
                best_count >= 0.70 * max(1, total) and
                best_count >= runner + 4 else None)
    touched = {uid for uid, count in counts.items() if count >= 2}
    touched.update(uid for uid in wheel_hits if uid)
    if wheel_uid and body_uid and wheel_uid != body_uid:
        return None, touched, "conflict"
    if wheel_uid:
        return wheel_uid, touched, "wheel-pair"
    if body_uid:
        return body_uid, touched, "lower-body-estimate"
    return None, touched, "uncertain"


def annotate_vehicle_zones(vehicles, zones, inside, frame_shape):
    height, width = frame_shape[:2]
    for vehicle in vehicles:
        vehicle["image_size"] = (width, height)
        candidate, touched, basis = locate_vehicle_zone(vehicle, zones, inside)
        vehicle["zone_candidate"] = candidate
        vehicle["zone_touched"] = sorted(touched)
        vehicle["zone_basis"] = basis
    return vehicles
