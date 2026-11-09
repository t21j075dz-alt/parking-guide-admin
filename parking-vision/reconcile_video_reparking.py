# -*- coding: utf-8 -*-
"""Keep recorded-video vehicle sessions in sync with independently verified stalls.

The live camera's tracker remains unchanged. The recorded stall state machine
is allowed to reconcile an EXITING vehicle to PARKED only when it confirms a
STOPPED stall for the exact same currently tracked vehicle. This is deliberately
stricter than "any occupied stall implies a parked vehicle".
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

MIN_CONFIRMATION_CONFIDENCE = 0.35


def reconcile_confirmed_video_reparking(tracker, recorded_machine, detections, now):
    """Return vehicle-session change rows after a confirmed re-parking event.

    Safety requirements:
    * recorded_machine.update() has already processed THIS frame;
    * stall phase is 'stopped' (not merely occupied/parking_in/unknown);
    * one fresh, monitored, verified and stopped car is bound to that stall;
    * exact stable track ID matches the stall's owning ID;
    * no other visible verified car is claiming the same stall;
    * no existing PARKED session claims this same stall;
    * only EXITING sessions are reconciled; never fabricate a new vehicle ID.

    The passed live/recorded tracker's historical observations and IDs survive.
    """
    eligible = []
    for detection in detections:
        tid = detection.get("track_id")
        uid = detection.get("demo_zone")
        if (tid is None or not uid
                or detection.get("monitored") is not True
                or detection.get("night_verified") is not True
                or float(detection.get("confidence", 0)) < MIN_CONFIRMATION_CONFIDENCE
                or detection.get("demo_stopped") is not True):
            continue
        eligible.append((int(tid), uid, detection))

    # Duplicated IDs or two cars in one space are ambiguous. Do not guess.
    ids = Counter(tid for tid, _, _ in eligible)
    zones = Counter(uid for _, uid, _ in eligible)
    events = []
    for tid, uid, detection in eligible:
        if ids[tid] != 1 or zones[uid] != 1:
            continue
        stall = recorded_machine.stalls.get(uid)
        entry = tracker.vehicles.get(tid)
        if (stall is None or entry is None
                or stall.phase != "stopped" or stall.track_id != tid
                or entry.phase != "exiting"
                or abs(entry.seen_monotonic - float(now)) > 1e-6):
            continue
        if any(other_tid != tid and other.phase == "parked"
               and other.space_uid == uid
               for other_tid, other in tracker.vehicles.items()):
            continue
        # The recorded machine already required >=5 seconds of continuous
        # image-derived zone association and evidence that this vehicle stopped.
        # Reuse that proof instead of demanding unavailable monitor zone votes.
        entry.phase = "parked"
        entry.space_uid = uid
        entry.park_anchor = detection["point"]
        entry.parked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry.candidate_uid = None
        entry.candidate_since = 0.0
        entry.candidate_started_at = None
        entry.left_space_at = None
        entry.outside_since = 0.0
        entry.outside_started_at = None
        detection["confirmed_parked_space"] = uid
        detection["repark_confirmed_by_recorded_stall"] = True
        events.append(entry.row())
    return events
