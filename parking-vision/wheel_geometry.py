#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixed-camera wheel contact estimator.

Detects *candidates* using circularity and local contrast inside a YOLO vehicle
box. It is NOT a separately trained wheel/keypoint model. Return [] whenever
two plausible wheels cannot be seen; no invented wheel locations are allowed.
"""
from __future__ import annotations


def estimate_wheel_contacts(frame, bbox):
    """Return two normalized wheel-ground contacts, or [] when uncertain.

    Only suitable for sufficiently large side/three-quarter-view vehicles.
    Cropped, distant, occluded and front-on vehicles remain unverified.
    """
    import cv2
    import numpy as np

    if frame is None or bbox is None or len(bbox) != 4:
        return []
    image_h, image_w = frame.shape[:2]
    x1, y1, x2, y2 = [float(value) for value in bbox]
    # A partially off-screen car made roof/window highlights look like
    # circular wheels in the 2026-10-29 field recording. Reject cropped
    # vehicle boxes instead of inventing two wheel-ground points.
    edge_margin = 3
    if (x1 <= edge_margin or y1 <= edge_margin or
            x2 >= image_w - edge_margin or y2 >= image_h - edge_margin):
        return []
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(image_w, int(x2)), min(image_h, int(y2))
    width, height = x2 - x1, y2 - y1
    if width < 115 or height < 65:
        return []

    top = y1 + int(height * 0.32)
    roi = frame[top:y2, x1:x2]
    if roi.shape[0] < 40:
        return []
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
    minimum = max(7, round(0.065 * height))
    maximum = max(minimum + 3, round(0.205 * height))
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=max(23, int(width * 0.23)),
        param1=100, param2=18, minRadius=minimum, maxRadius=maximum,
    )
    if circles is None:
        return []

    yy, xx = np.ogrid[:gray.shape[0], :gray.shape[1]]
    candidates = []
    for rx, ry, radius in circles[0]:
        rx = float(rx)
        cy = float(ry) + top - y1
        radius = float(radius)
        if not (0.16 * width <= rx <= 0.97 * width
                and 0.44 * height <= cy <= 0.97 * height):
            continue
        distance_sq = (xx - rx) ** 2 + (yy - float(ry)) ** 2
        center = distance_sq <= (0.85 * radius) ** 2
        surround = ((distance_sq >= (1.30 * radius) ** 2)
                    & (distance_sq <= (1.85 * radius) ** 2))
        if center.sum() < 30 or surround.sum() < 30:
            continue
        dark_fraction = float((gray[center] < 100).mean())
        contrast = float(gray[surround].mean() - gray[center].mean())
        if dark_fraction < 0.20 or contrast < 11:
            continue
        score = min(1.0, dark_fraction) + min(contrast, 85) / 130.0
        candidates.append((rx, cy, radius, score))

    pairs = []
    for i, first in enumerate(candidates):
        for second in candidates[i + 1:]:
            left, right = sorted((first, second), key=lambda wheel: wheel[0])
            separation = (right[0] - left[0]) / width
            if not 0.28 <= separation <= 0.83:
                continue
            if abs(left[1] - right[1]) > 0.53 * height:
                continue
            if max(left[2], right[2]) / min(left[2], right[2]) > 2.0:
                continue
            # Geometric preference only: the darkness tests above are mandatory.
            offset = abs(left[0] / width - 0.40) + abs(right[0] / width - 0.86)
            pairs.append((left[3] + right[3] - 0.8 * offset, left, right))

    if not pairs:
        return []
    _, left, right = max(pairs, key=lambda pair: pair[0])
    contacts = []
    for cx, cy, radius, _ in (left, right):
        contacts.append((
            min(1.0, max(0.0, (x1 + cx) / image_w)),
            min(1.0, max(0.0, (y1 + cy + 0.65 * radius) / image_h)),
        ))
    return contacts
