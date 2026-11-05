# -*- coding: utf-8 -*-
"""Conservative temporal agreement of two camera-image parking cues.

Neither a YOLO box nor a visible mask proves the true tyre contact position.
This optional VIDEO EXPERIMENT deliberately returns UNKNOWN when contradictory
and never assumes a missing observation means that a stall is empty.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CandidateHistory:
    uid: str
    since: float
    last_seen: float
    frames: int


class ParkingGeometryFusion:
    """Require consistency before using a mask-only stall suggestion.

    Strong agreement between independently computed lower-edge estimates
    can be accepted immediately; a mask-only suggestion is provisional
    until a continuous interval of >=2s with >=5 observations.
    """

    def __init__(self, hold_seconds=2.0, min_frames=5, max_gap=.75):
        self.hold_seconds = float(hold_seconds)
        self.min_frames = int(min_frames)
        self.max_gap = float(max_gap)
        self.histories = {}

    def resolve(self, detection, legacy_uid, legacy_touched, now):
        legacy_touched = set(legacy_touched or ())
        mask_uid = detection.get("segmentation_candidate")
        mask_touched = set(detection.get("segmentation_touched") or ())
        raw = detection.get("track_id")
        result_touched = legacy_touched | mask_touched
        if raw is None:
            return legacy_uid, result_touched, "no-track"

        identity = int(raw)
        existing = self.histories.get(identity)
        if (existing is not None and
                float(now)-existing.last_seen > self.max_gap):
            self.histories.pop(identity, None)
            existing = None

        if legacy_uid and mask_uid and legacy_uid != mask_uid:
            self.histories.pop(identity, None)
            # Two independent estimates disagree: never pick a winner.
            return None, result_touched | {legacy_uid, mask_uid}, "conflict"

        if legacy_uid:
            self.histories.pop(identity, None)
            if mask_uid == legacy_uid:
                return legacy_uid, result_touched, "agreement"
            # No confident mask available: retain the legacy proposal;
            # this is not a new source of evidence.
            return legacy_uid, result_touched, "legacy"

        if not mask_uid:
            self.histories.pop(identity, None)
            return None, result_touched, "unknown"

        trustworthy = (
            detection.get("segmentation_contour") is not None
            and float(detection.get("segmentation_confidence") or 0.) >= .80
            and float(detection.get("segmentation_match_iou") or 0.) >= .80
            and len(detection.get("segmentation_bottom_points") or ()) >= 7
            and (not legacy_touched or mask_uid in legacy_touched)
        )
        if not trustworthy:
            self.histories.pop(identity, None)
            return None, result_touched | {mask_uid}, "mask-uncertain"

        if existing and existing.uid == mask_uid:
            existing.frames += 1
            existing.last_seen = float(now)
        else:
            existing = CandidateHistory(
                uid=mask_uid, since=float(now), last_seen=float(now), frames=1)
            self.histories[identity] = existing
        if (existing.frames >= self.min_frames and
                float(now)-existing.since >= self.hold_seconds):
            return mask_uid, result_touched, "mask-temporal"
        return None, result_touched | {mask_uid}, "mask-pending"

    def forget_stale(self, now, ttl=12.0):
        for tid, history in list(self.histories.items()):
            if float(now)-history.last_seen > ttl:
                del self.histories[tid]
