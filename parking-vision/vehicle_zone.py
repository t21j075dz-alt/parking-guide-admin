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




def _point_to_segment_distance(point, a, b):
    """Normalized image distance from a contact point to a zone edge."""
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    fraction = 0.0 if length_sq < 1e-12 else max(
        0., min(1., ((px - ax) * dx + (py - ay) * dy) / length_sq)
    )
    return ((px - (ax + fraction * dx)) ** 2 +
            (py - (ay + fraction * dy)) ** 2) ** .5


def nearest_monitored_spaces(detection, zones, inside, distance_limit=.055):
    """Potential stall interaction even before the wheels cross its border.

    A rectangular vehicle detection need not mean its wheels are there.
    This defines monitoring relevance, not a definite occupied state.
    """
    size = detection.get("image_size")
    box = detection.get("bbox")
    if not size or not box or len(box) != 4:
        return set()
    width, height = size
    if width <= 0 or height <= 0:
        return set()
    x1, _, x2, y2 = [float(v) for v in box]
    contact_points = [((x1 + (x2 - x1) * f) / width, y2 / height)
                      for f in (0.30, 0.50, 0.70)]
    nearby = set()
    for uid, polygon in zones.items():
        if any(inside(point, polygon) for point in contact_points):
            nearby.add(uid)
            continue
        if any(min(_point_to_segment_distance(point, a, b)
                   for a, b in zip(polygon, polygon[1:] + polygon[:1]))
               <= distance_limit for point in contact_points):
            nearby.add(uid)
    return nearby


def is_monitored_vehicle(vehicle, zones, inside, entry_zone=None,
                         exit_zone=None):
    """Keep the parking/entrance region; reject distant false car tracks.

    Historical/offline detections lacking an image bounding box pass through.
    """
    if "bbox" not in vehicle or "image_size" not in vehicle:
        return True
    if vehicle.get("zone_candidate") or vehicle.get("zone_touched"):
        return True
    if vehicle.get("zone_nearby"):
        return True
    # A real car needs several moving frames BEFORE its wheels enter the
    # stall. Include a modest approach corridor around the calibrated zones
    # for motion verification. This never confirms occupancy on its own.
    if nearest_monitored_spaces(vehicle, zones, inside, distance_limit=.13):
        vehicle["approach_only"] = True
        return True
    for region in (entry_zone or [], exit_zone or []):
        if len(region) >= 3 and inside(vehicle.get("point", (-1., -1.)), region):
            return True
    return False

def annotate_vehicle_zones(vehicles, zones, inside, frame_shape):
    height, width = frame_shape[:2]
    for vehicle in vehicles:
        vehicle["image_size"] = (width, height)
        candidate, touched, basis = locate_vehicle_zone(vehicle, zones, inside)
        vehicle["zone_candidate"] = candidate
        vehicle["zone_touched"] = sorted(touched)
        vehicle["zone_basis"] = basis
        vehicle["zone_nearby"] = sorted(nearest_monitored_spaces(
            vehicle, zones, inside))
    return vehicles
