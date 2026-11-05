# -*- coding: utf-8 -*-
"""Conservative time-window fusion of parking-zone hypotheses.

Visible segmentation masks are NOT a measurement of tyre/ground contact.
The fused proposal is available only in isolated recorded-video experiments.
A weak or absent mask cannot by itself certify a stall as occupied or free.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CandidateHistory:
    uid: str
    since: float
    last_seen: float
    frames: int
    last_positive: float


class ParkingGeometryFusion:
    """Accumulate repeated mask evidence through brief confidence dips.

    The old implementation discarded a valid history on ONE low-confidence
    frame and even when the legacy box began agreeing with the mask. Neither
    is a reason to forget the same physical vehicle's zone hypothesis.

    Requirements for a mask-only candidate:
      - same stable vehicle ID and the same stall
      - no competing legacy stall
      - mask confidence >= 0.78 and alignment >= 0.80 on positive frames
      - at least five distinct positive frames over >= 1.6 video seconds
      - no observation gap > 0.75 seconds between positive/weak samples

    Low-quality frames *pause* the positive counter; they never authorize
    occupancy. Contradictory stalls or prolonged missing data reset it.
    """

    def __init__(self, hold_seconds=1.6, min_frames=5, max_gap=.75,
                 min_mask_confidence=.78):
        self.hold_seconds = float(hold_seconds)
        self.min_frames = int(min_frames)
        self.max_gap = float(max_gap)
        self.min_mask_confidence = float(min_mask_confidence)
        self.histories = {}

    def _evidence(self, identity, uid, now, positive):
        previous = self.histories.get(identity)
        if previous is None or previous.uid != uid:
            if not positive:
                return None
            current = CandidateHistory(uid=uid, since=now, last_seen=now,
                                       frames=1, last_positive=now)
            self.histories[identity] = current
            return current

        # A weak frame may maintain a recent candidate but cannot increase
        # positive evidence or extend the candidate's original start time.
        previous.last_seen = now
        if positive and now > previous.last_positive + 1.e-6:
            previous.frames += 1
            previous.last_positive = now
        return previous

    def resolve(self, detection, legacy_uid, legacy_touched, now):
        now = float(now)
        legacy_touched = set(legacy_touched or ())
        mask_uid = detection.get("segmentation_candidate")
        mask_touched = set(detection.get("segmentation_touched") or ())
        result_touched = legacy_touched | mask_touched
        raw = detection.get("track_id")
        if raw is None:
            # Unidentified detections never create mask-only occupancy.
            return legacy_uid, result_touched, "no-track"
        identity = int(raw)

        existing = self.histories.get(identity)
        if existing is not None and (now < existing.last_seen or
                                     now - existing.last_seen > self.max_gap):
            self.histories.pop(identity, None)
            existing = None

        if legacy_uid and mask_uid and legacy_uid != mask_uid:
            self.histories.pop(identity, None)
            return None, result_touched | {legacy_uid, mask_uid}, "conflict"

        if legacy_uid:
            # A positive legacy box confirming the SAME stall is supportive,
            # not an instruction to erase the mask-only history.
            if existing is not None and existing.uid != legacy_uid:
                self.histories.pop(identity, None)
            if mask_uid == legacy_uid:
                self._evidence(identity, legacy_uid, now, positive=True)
                return legacy_uid, result_touched, "agreement"
            self._evidence(identity, legacy_uid, now, positive=False)
            return legacy_uid, result_touched, "legacy"

        if not mask_uid:
            # Do not extend the history through wholly missing evidence.
            # The next reliable observation may reuse it within max_gap.
            return None, result_touched, "unknown"

        # Never let a mask-only hypothesis assign a stall that NONE of the
        # legacy box's sampled contact points touched.
        if legacy_touched and mask_uid not in legacy_touched:
            self.histories.pop(identity, None)
            return None, result_touched | {mask_uid}, "mask-uncertain"

        if existing is not None and existing.uid != mask_uid:
            self.histories.pop(identity, None)

        valid_geometry = (
            detection.get("segmentation_contour") is not None
            and float(detection.get("segmentation_match_iou") or 0.) >= .80
            and len(detection.get("segmentation_bottom_points") or ()) >= 7
        )
        strong = (valid_geometry
                  and float(detection.get("segmentation_confidence") or 0.)
                  >= self.min_mask_confidence)
        current = self._evidence(identity, mask_uid, now,
                                 positive=strong if valid_geometry else False)

        if not strong:
            # Keep the tentative hypothesis for brief low-confidence frames.
            # Do NOT return a previously accepted zone on weak evidence.
            return None, result_touched | {mask_uid}, (
                "mask-weak-hold" if current is not None else "mask-uncertain")

        if current is not None and (current.frames >= self.min_frames
                                    and now - current.since >= self.hold_seconds):
            return mask_uid, result_touched, "mask-temporal"
        return None, result_touched | {mask_uid}, "mask-pending"

    def forget_stale(self, now, ttl=12.0):
        for tid, history in list(self.histories.items()):
            if float(now) - history.last_seen > ttl:
                del self.histories[tid]
