# -*- coding: utf-8 -*-
"""Optional vehicle-instance segmentation for research comparisons.

The segmentation model NEVER sets parking occupancy or vehicle tracking IDs.
It annotates independently tracked YOLO detections with matched visible-body
contours and approximate lower-silhouette image points. These are not tyre
contacts or a measured vehicle ground footprint.
"""
from __future__ import annotations

import csv
from math import isfinite
from pathlib import Path


FOUR_WHEEL = {"car", "van", "truck", "bus", "vehicle"}
TWO_WHEEL = {"motorcycle", "bicycle", "tricycle", "awning_tricycle"}


def _group(name):
    value = str(name).lower().strip().replace("-", "_")
    if value in FOUR_WHEEL:
        return "four_wheel"
    if value in TWO_WHEEL:
        return "two_wheel"
    return None


def box_iou(left, right):
    """Intersection over union for two xyxy boxes."""
    if left is None or right is None or len(left) != 4 or len(right) != 4:
        return 0.0
    a, b, c, d = map(float, left)
    e, f, g, h = map(float, right)
    area1, area2 = max(0, c - a) * max(0, d - b), max(0, g - e) * max(0, h - f)
    intersect = max(0, min(c, g) - max(a, e)) * max(0, min(d, h) - max(b, f))
    return intersect / max(1e-9, area1 + area2 - intersect)


def lower_silhouette_points(contour, frame_shape, columns=9):
    """Image-normalized lower *visible* contour points (not ground contacts).

    Polygon edges are intersected with vertical sample lines. This is safer
    than treating a detection rectangle's y2 as the bottom of every column.
    """
    height, width = frame_shape[:2]
    if width <= 0 or height <= 0 or len(contour) < 3 or columns < 1:
        return []
    xs = [float(point[0]) for point in contour]
    low, high = min(xs), max(xs)
    if high - low < 2:
        return []
    points = []
    for index in range(columns):
        x = low + (high - low) * (index + .5) / columns
        intersections = []
        for a, b in zip(contour, contour[1:] + contour[:1]):
            ax, ay = float(a[0]), float(a[1])
            bx, by = float(b[0]), float(b[1])
            if abs(bx - ax) < 1e-9:
                if abs(x - ax) < 1e-6:
                    intersections.extend((ay, by))
                continue
            t = (x - ax) / (bx - ax)
            if 0.0 <= t <= 1.0:
                intersections.append(ay + t * (by - ay))
        if intersections:
            points.append((max(0., min(1., x / width)),
                           max(0., min(1., max(intersections) / height))))
    return points


def estimate_mask_zone(points, zones, inside):
    """Diagnostic mask-zone candidate only; NOT approved for occupancy."""
    if not points or not zones or inside is None:
        return None, set()
    votes = {uid: 0 for uid in zones}
    for point in points:
        hits = [uid for uid, polygon in zones.items() if inside(point, polygon)]
        if len(hits) == 1:
            votes[hits[0]] += 1
    ranks = sorted(votes.items(), key=lambda pair: pair[1], reverse=True)
    if not ranks:
        return None, set()
    first, count = ranks[0]
    second = ranks[1][1] if len(ranks) > 1 else 0
    touched = {uid for uid, votes_count in ranks if votes_count >= 2}
    total = sum(votes.values())
    candidate = (first if count >= 5 and count >= .65 * total
                 and count >= 1.5 * max(1, second) else None)
    return candidate, touched


def best_visible_bbox(detection, min_seg_confidence=.65):
    """Prefer the mask-tight box ONLY for video overlay, not state decisions.

    A visible mask is not a physical footprint. If it is poorly aligned or
    too incomplete, retain the original detector box rather than jump.
    """
    original = detection.get("bbox")
    mask_box = detection.get("segmentation_bbox")
    if not original or not mask_box:
        return original
    if (float(detection.get("segmentation_confidence", 0)) < min_seg_confidence or
            float(detection.get("segmentation_match_iou", 0)) < .70):
        return original
    original_area = max(0., original[2]-original[0]) * max(0., original[3]-original[1])
    mask_area = max(0., mask_box[2]-mask_box[0]) * max(0., mask_box[3]-mask_box[1])
    if original_area <= 0 or not (.50 <= mask_area / original_area <= 1.20):
        return original
    if box_iou(original, mask_box) < .45:
        return original
    return mask_box


def attach_vehicle_contours(detections, result, frame_shape, zones=None,
                            inside=None, min_iou=.30):
    """Match independent seg detections to existing tracks, one-to-one.

    Result is Ultralytics instance-seg Results, using masks.xy in original
    pixel coordinates. No new track IDs or parking-state changes are made.
    """
    # Explicitly record that segmentation was attempted, even for misses.
    for detection in detections:
        detection["segmentation_checked"] = True
    if result is None or getattr(result, "boxes", None) is None:
        return 0
    masks = getattr(result, "masks", None)
    if masks is None or not getattr(masks, "xy", None):
        return 0
    boxes = result.boxes.xyxy.cpu().tolist()
    classes = result.boxes.cls.int().cpu().tolist()
    confidences = result.boxes.conf.cpu().tolist()
    contours = masks.xy
    height, width = frame_shape[:2]
    candidates = []
    for det_index, detection in enumerate(detections):
        det_group = _group(detection.get("name"))
        if det_group is None or not detection.get("bbox"):
            continue
        for seg_index, (box, class_id, confidence, contour) in enumerate(
                zip(boxes, classes, confidences, contours)):
            segment_group = _group(result.names[int(class_id)])
            if segment_group is None or segment_group != det_group:
                continue
            if len(contour) < 3:
                continue
            overlap = box_iou(detection["bbox"], box)
            if overlap >= min_iou:
                candidates.append((overlap * (0.5 + float(confidence) / 2.),
                                   overlap, det_index, seg_index))
    used_detections, used_segments = set(), set()
    matched = 0
    for _, overlap, det_index, seg_index in sorted(candidates, reverse=True):
        if det_index in used_detections or seg_index in used_segments:
            continue
        raw_contour = contours[seg_index]
        if any(not isfinite(float(p[0])) or not isfinite(float(p[1]))
               for p in raw_contour):
            continue
        polygon = [(max(0., min(float(width - 1), float(p[0]))),
                    max(0., min(float(height - 1), float(p[1]))))
                   for p in raw_contour]
        if len(set(polygon)) < 3:
            continue
        points = lower_silhouette_points(polygon, frame_shape)
        if len(points) < 5:
            continue
        zone, touched = estimate_mask_zone(points, zones, inside)
        detection = detections[det_index]
        detection["segmentation_contour"] = polygon
        detection["segmentation_bbox"] = [
            min(p[0] for p in polygon), min(p[1] for p in polygon),
            max(p[0] for p in polygon), max(p[1] for p in polygon),
        ]
        detection["segmentation_bottom_points"] = points
        detection["segmentation_candidate"] = zone
        detection["segmentation_touched"] = sorted(touched)
        detection["segmentation_match_iou"] = round(overlap, 4)
        detection["segmentation_confidence"] = round(float(confidences[seg_index]), 4)
        used_detections.add(det_index)
        used_segments.add(seg_index)
        matched += 1
    return matched



def tracked_segment_detections(result, frame_shape, allowed_names, class_aliases,
                               zones=None, inside=None):
    """Use ONE segmentation result as both detection AND tracking evidence.

    There is no second-model IoU association: boxes, masks and YOLO raw track
    IDs share their native Results indices. This avoids intermittent mismatch
    during wide changes of vehicle orientation.
    """
    if result is None or getattr(result, "boxes", None) is None:
        return []
    height, width = frame_shape[:2]
    if height <= 0 or width <= 0:
        return []
    boxes_obj = result.boxes
    boxes = boxes_obj.xyxy.cpu().tolist()
    classes = boxes_obj.cls.int().cpu().tolist()
    confidences = boxes_obj.conf.cpu().tolist()
    raw_ids = (boxes_obj.id.int().cpu().tolist()
               if getattr(boxes_obj, "id", None) is not None
               else [None] * len(boxes))
    masks_obj = getattr(result, "masks", None)
    polygons = (getattr(masks_obj, "xy", None) if masks_obj is not None
                else None)
    output = []
    for index, (bbox, class_id, confidence, raw_id) in enumerate(
            zip(boxes, classes, confidences, raw_ids)):
        name = str(result.names[int(class_id)]).lower().strip().replace("-", "_")
        name = class_aliases.get(name, name)
        if name not in allowed_names:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            continue
        x1, x2 = max(0., min(x1, width-1.)), max(0., min(x2, width-1.))
        y1, y2 = max(0., min(y1, height-1.)), max(0., min(y2, height-1.))
        if x2-x1 < 3 or y2-y1 < 3:
            continue
        box = [x1, y1, x2, y2]
        detection = {
            "name": name, "point": ((x1+x2)/(2*width), y2/height),
            "bottom_points": [((x1+(x2-x1)*f)/width, y2/height)
                              for f in (.25,.5,.75)],
            "track_id": int(raw_id) if raw_id is not None else None,
            "confidence": float(confidence), "bbox": box,
            "segmentation_checked": True, "detection_source": "segment-track",
        }
        if polygons is not None and index < len(polygons):
            raw_contour = polygons[index]
            if (len(raw_contour) >= 3 and
                    all(isfinite(float(p[0])) and isfinite(float(p[1]))
                        for p in raw_contour)):
                polygon = [(max(0., min(width-1., float(p[0]))),
                            max(0., min(height-1., float(p[1]))))
                           for p in raw_contour]
                if len(set(polygon)) >= 3:
                    points = lower_silhouette_points(polygon, frame_shape)
                    if len(points) >= 5:
                        mask_box = [min(p[0] for p in polygon),
                                    min(p[1] for p in polygon),
                                    max(p[0] for p in polygon),
                                    max(p[1] for p in polygon)]
                        candidate, touched = estimate_mask_zone(
                            points, zones, inside)
                        detection.update({
                            "segmentation_contour": polygon,
                            "segmentation_bbox": mask_box,
                            "segmentation_bottom_points": points,
                            "segmentation_candidate": candidate,
                            "segmentation_touched": sorted(touched),
                            "segmentation_confidence": float(confidence),
                            "segmentation_match_iou": round(
                                box_iou(box, mask_box), 4),
                        })
        output.append(detection)
    return output


def draw_vehicle_contours(frame, detections):
    """Overlay optional mask polygons on a COPY of the camera frame."""
    import cv2
    import numpy as np

    canvas = frame.copy()
    height, width = frame.shape[:2]
    for detection in detections:
        contour = detection.get("segmentation_contour") or []
        if len(contour) < 3:
            continue
        polygon = np.array(contour, dtype=np.int32).reshape((-1, 1, 2))
        layer = canvas.copy()
        cv2.fillPoly(layer, [polygon], (40, 175, 255))
        cv2.addWeighted(layer, .24, canvas, .76, 0, canvas)
        cv2.polylines(canvas, [polygon], True, (0, 230, 255), 2, cv2.LINE_AA)
        for x, y in detection.get("segmentation_bottom_points", []):
            cv2.circle(canvas, (min(width - 1, int(x * width)),
                                min(height - 1, int(y * height))),
                       2, (245, 80, 250), -1, cv2.LINE_AA)
    return canvas


class SegmentationDiagnosticRecorder:
    """Save numeric comparisons only, no masks, plates or cropped images."""

    FIELDS = ("video_seconds", "stable_track_id", "raw_track_id",
              "legacy_zone", "segmentation_zone", "segmentation_match_iou",
              "segmentation_confidence", "lower_points", "match_state",
              "id_mask_bridged", "display_bbox_source")

    def __init__(self, folder):
        self.stream = open(Path(folder) / "車両輪郭_比較診断.csv", "w",
                           encoding="utf-8-sig", newline="")
        self.writer = csv.DictWriter(self.stream, fieldnames=self.FIELDS)
        self.writer.writeheader()

    def write(self, detections, video_seconds):
        for det in detections:
            self.writer.writerow({
                "video_seconds": f"{float(video_seconds):.3f}",
                "stable_track_id": det.get("track_id"),
                "raw_track_id": det.get("raw_track_id"),
                "legacy_zone": det.get("zone_candidate") or "",
                "segmentation_zone": det.get("segmentation_candidate") or "",
                "segmentation_match_iou": det.get("segmentation_match_iou", ""),
                "segmentation_confidence": det.get("segmentation_confidence", ""),
                "lower_points": len(det.get("segmentation_bottom_points") or []),
                "match_state": ("matched" if det.get("segmentation_contour")
                                else "unmatched"),
                "id_mask_bridged": "yes" if det.get("id_mask_bridged") else "no",
                "display_bbox_source": ("segmentation" if
                                        det.get("display_bbox") is not None else
                                        "detector"),
            })

    def close(self):
        self.stream.close()
