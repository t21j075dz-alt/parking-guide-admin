# -*- coding: utf-8 -*-
"""Conservative temporal fusion of visible silhouette and box-bottom evidence.

A 2-D segmentation mask is NOT a measurement of the car's ground contact
points. For that reason, neither cue alone can instantly assign a parking
space when the cues disagree or only one is available. Repeated, unambiguous
observations are required. This module does not control track identities.
"""
from __future__ import annotations

from dataclasses import dataclass

from recorded_parking_states import bottom_footprint_candidate


@dataclass
class PendingZone:
    zone: str
    first: float
    last: float
    frames: int = 1


class TemporalZoneFusion:
    """Per-stable-ID confirmation; calls must follow video time order."""

    def __init__(self, single_source_seconds=1.25, single_source_frames=5,
                 max_gap_seconds=.65, min_mask_confidence=.65,
                 min_mask_box_iou=.70):
        self.single_source_seconds = float(single_source_seconds)
        self.single_source_frames = int(single_source_frames)
        self.max_gap_seconds = float(max_gap_seconds)
        self.min_mask_confidence = float(min_mask_confidence)
        self.min_mask_box_iou = float(min_mask_box_iou)
        self.pending = {}
        self.last_seen = {}

    def reset(self):
        self.pending.clear()
        self.last_seen.clear()

    def update(self, detections, zones, inside, now):
        """Add diagnostic fused_* keys; original bbox and zone fields unchanged.

        Both agree -> candidate is accepted immediately, but the downstream
        5-second parking-state machine still makes the occupation decision.

        One cue only -> require >=1.25 s and >=5 video observations.
        Disagreement -> unknown; include BOTH nearby spaces in uncertainty.
        No validated mask -> no claim of a better ground estimate.
        """
        now = float(now)
        for sid in list(self.last_seen):
            if now - self.last_seen[sid] > 12.0:
                del self.last_seen[sid]
                self.pending.pop(sid, None)

        for det in detections:
            legacy, legacy_touched, _ = bottom_footprint_candidate(
                det, zones, inside
            )
            seg_valid = bool(
                det.get("segmentation_contour")
                and float(det.get("segmentation_confidence") or 0)
                    >= self.min_mask_confidence
                and float(det.get("segmentation_match_iou") or 0)
                    >= self.min_mask_box_iou
                and len(det.get("segmentation_bottom_points") or ()) >= 7
            )
            seg = det.get("segmentation_candidate") if seg_valid else None
            seg_touched = (set(det.get("segmentation_touched") or [])
                           if seg_valid else set())
            touched = set(legacy_touched) | seg_touched
            if legacy:
                touched.add(legacy)
            if seg:
                touched.add(seg)
            tid = det.get("track_id")
            source = "unresolved"
            candidate = None
            conflict = bool(legacy and seg and legacy != seg)
            if conflict:
                source = "conflict"
            elif legacy and seg and legacy == seg:
                candidate = legacy
                source = "bbox+mask"
            else:
                only = legacy or seg
                if only:
                    source = "bbox-only" if legacy else "mask-only"
                    if tid is not None:
                        sid = int(tid)
                        old = self.pending.get(sid)
                        if (old is not None and old.zone == only and
                                0 <= now - old.last <= self.max_gap_seconds):
                            old.last = now
                            old.frames += 1
                        else:
                            old = PendingZone(only, now, now)
                        self.pending[sid] = old
                        if (old.frames >= self.single_source_frames and
                                now - old.first >= self.single_source_seconds):
                            candidate = only
                            source += "-confirmed"
                elif not seg_valid:
                    source = "mask-unavailable"

            if tid is not None:
                sid = int(tid)
                self.last_seen[sid] = now
                if conflict or (candidate is not None and source == "bbox+mask"):
                    # A new agreement or explicit disagreement must not
                    # resurrect a stale single-source candidate later.
                    self.pending.pop(sid, None)
                elif legacy is None and seg is None:
                    self.pending.pop(sid, None)
            det["zone_fusion_evaluated"] = True
            det["fused_zone_candidate"] = candidate
            det["fused_zone_touched"] = sorted(touched)
            det["fused_zone_basis"] = source
            det["fused_zone_conflict"] = conflict
        return detections
