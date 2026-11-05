# -*- coding: utf-8 -*-
"""Display-only stabilisation of vehicle bounding boxes and orientation axes.

Bounding boxes naturally change aspect ratio when a car turns; they should not
be frozen. Low-pass smoothing suppresses one-frame wobble and short-lived mask
extent changes without altering raw detection/parking geometry. The principal
axis is NOT a front/rear heading and is NOT a tire-ground estimate.
"""
from __future__ import annotations

from math import atan2, cos, exp, hypot, sin, sqrt

from vehicle_segmentation import best_visible_bbox, box_iou


def visible_major_axis(contour, min_ratio=1.28):
    """Return (cx, cy, long_length, axial_angle_rad) or None.

    OpenCV minimum-area rectangle provides a symmetric long axis. For a
    nearly square projected silhouette there is no stable orientation, so
    leave the angle unknown instead of displaying an arbitrary 90deg flip.
    """
    if not contour or len(contour) < 4:
        return None
    import cv2
    import numpy as np

    polygon = np.asarray(contour, dtype=np.float32).reshape(-1, 1, 2)
    (cx, cy), (a, b), degrees = cv2.minAreaRect(polygon)
    long_len, short_len = max(a, b), min(a, b)
    if short_len <= 0 or long_len / short_len < min_ratio:
        return None
    box = cv2.boxPoints(((cx, cy), (a, b), degrees))
    longest = None
    for p, q in zip(box, list(box[1:]) + [box[0]]):
        delta = (float(q[0]-p[0]), float(q[1]-p[1]))
        length = hypot(*delta)
        if longest is None or length > longest[0]:
            longest = (length, delta)
    angle = atan2(longest[1][1], longest[1][0]) % 3.141592653589793
    return float(cx), float(cy), float(long_len), angle


class TrackingPresentation:
    def __init__(self, box_tau=.30, angle_tau=.40, max_gap=1.3):
        self.box_tau = float(box_tau)
        self.angle_tau = float(angle_tau)
        self.max_gap = float(max_gap)
        self.last = {}

    def reset(self):
        self.last.clear()

    def update(self, detections, now, image_shape):
        height, width = image_shape[:2]
        now = float(now)
        for sid in list(self.last):
            if now - self.last[sid]["time"] > 3.0:
                del self.last[sid]

        for det in detections:
            proposed = best_visible_bbox(det)
            if proposed is None or len(proposed) != 4:
                continue
            target = [float(v) for v in proposed]
            tid = det.get("track_id")
            stable = int(tid) if tid is not None else None
            prior = self.last.get(stable) if stable is not None else None
            dt = now-prior["time"] if prior is not None else None
            smooth = (prior is not None and dt is not None and
                      0 < dt <= self.max_gap and
                      box_iou(target, prior["box"]) >= .08)
            if smooth:
                alpha = max(.05, min(1., 1. - exp(-dt / self.box_tau)))
                left = [(1.-alpha)*p+alpha*t
                        for p,t in zip(prior["box"], target)]
                display = [
                    max(0., min(width-1., left[0])),
                    max(0., min(height-1., left[1])),
                    max(0., min(width-1., left[2])),
                    max(0., min(height-1., left[3])),
                ]
            else:
                display = target

            # A long axis has 180-degree symmetry; double-angle averaging
            # prevents a flip when a turning car crosses 0/180 degrees.
            pose = visible_major_axis(det.get("segmentation_contour"))
            axis = None
            axis_state = None
            if pose is not None:
                cx,cy,length,angle = pose
                vx,vy = cos(2*angle),sin(2*angle)
                if smooth and prior.get("axis_state") is not None:
                    px,py = prior["axis_state"]
                    alpha = max(.05,min(1.,1.-exp(-dt/self.angle_tau)))
                    vx = (1-alpha)*px+alpha*vx
                    vy = (1-alpha)*py+alpha*vy
                    mag = hypot(vx,vy)
                    if mag > .10:
                        vx,vy = vx/mag,vy/mag
                angle = .5*atan2(vy,vx)
                dx,dy = .44*length*cos(angle),.44*length*sin(angle)
                axis = ((int(cx-dx),int(cy-dy)),
                        (int(cx+dx),int(cy+dy)))
                axis_state = (vx,vy)
            if stable is not None:
                self.last[stable] = {
                    "box": display, "time": now,
                    "axis_state": axis_state,
                }
            det["display_bbox"] = display
            det["display_bbox_source"] = (
                "smoothed-mask" if proposed is not det.get("bbox")
                else "smoothed-detector")
            if axis is not None:
                det["visible_long_axis"] = axis
                det["visible_axis_degrees"] = round(
                    (angle * 180/3.141592653589793) % 180,1)
            else:
                det.pop("visible_long_axis", None)
                det.pop("visible_axis_degrees", None)
        return detections
