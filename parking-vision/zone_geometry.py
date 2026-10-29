# -*- coding: utf-8 -*-
"""Validate fixed-camera parking polygons and repair click-order crossings."""
from __future__ import annotations

from math import atan2


def signed_area(points):
    return .5 * sum(a[0] * b[1] - b[0] * a[1]
                    for a, b in zip(points, points[1:] + points[:1]))


def normalize_corners(points):
    """Sort four arbitrary corner clicks around their centroid.

    Reject repeated, very small and non-convex quadrilaterals rather than
    silently generating a broken parking-space footprint.
    """
    if len(points) != 4:
        raise ValueError("四隅の4点を登録してください")
    coordinates = [[float(x), float(y)] for x, y in points]
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in coordinates):
        raise ValueError("座標は0～1の範囲にしてください")
    if len({(round(x, 5), round(y, 5)) for x, y in coordinates}) != 4:
        raise ValueError("同じ位置を複数回クリックしています")
    cx = sum(p[0] for p in coordinates) / 4
    cy = sum(p[1] for p in coordinates) / 4
    ordered = sorted(coordinates, key=lambda p: atan2(p[1] - cy, p[0] - cx))
    if abs(signed_area(ordered)) < 0.00005:
        raise ValueError("駐車枠が小さすぎる、または四隅がほぼ一直線です")
    signs = []
    for i in range(4):
        a, b, c = (ordered[i], ordered[(i+1)%4], ordered[(i+2)%4])
        cross = ((b[0]-a[0]) * (c[1]-b[1]) -
                 (b[1]-a[1]) * (c[0]-b[0]))
        if abs(cross) < 0.0000005:
            raise ValueError("四隅の形が崩れています。離れた4点で登録してください")
        signs.append(cross > 0)
    if len(set(signs)) != 1:
        raise ValueError("四隅が凸四角形になりません。区画線に沿って登録してください")
    return [[round(x, 5), round(y, 5)] for x, y in ordered]


def _inside(point, polygon):
    x, y = point
    hit = False
    for i, (a, b) in enumerate(polygon):
        c, d = polygon[(i+1)%len(polygon)]
        if (b > y) != (d > y) and x < (c - a) * (y - b) / (d - b) + a:
            hit = not hit
    return hit


def audit_zones(zones):
    """Print-only warnings; never mark a stall free from its shape alone."""
    warnings = []
    for uid, polygon in zones.items():
        area = abs(signed_area(polygon))
        width = max(p[0] for p in polygon) - min(p[0] for p in polygon)
        height = max(p[1] for p in polygon) - min(p[1] for p in polygon)
        if area < .00035 or width < .015 or height < .012:
            warnings.append(f"{uid}: 枠が非常に小さいため再登録を推奨します")
        if area > .35:
            warnings.append(f"{uid}: 枠が画面に対して大きすぎる可能性があります")
    # Sample overlap area, ignoring mere shared edges and rounding noise.
    overlaps = {}
    for yi in range(1, 60):
        for xi in range(1, 80):
            point = (xi/80, yi/60)
            matched = [uid for uid, poly in zones.items() if _inside(point, poly)]
            if len(matched) > 1:
                for i, a in enumerate(matched):
                    for b in matched[i+1:]:
                        key = tuple(sorted((a, b)))
                        overlaps[key] = overlaps.get(key, 0) + 1
    for (a, b), count in overlaps.items():
        if count >= 4:
            warnings.append(f"{a} と {b}: 駐車枠の登録範囲が重なっています（サンプル点{count}件）")
    return warnings
