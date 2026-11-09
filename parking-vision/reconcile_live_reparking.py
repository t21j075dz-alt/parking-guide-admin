# -*- coding: utf-8 -*-
"""Opt-in LIVE camera re-parking confirmation, without changing free-space logic.

This uses the same temporal evidence as recorded-video stall confirmation, but
ONLY to reconcile an existing EXITING stable ID after verified stationary evidence.
The live SpaceObserver remains the sole authority for published vacancy.
"""
from __future__ import annotations

from recorded_parking_states import RecordedParkingStateMachine
from reconcile_video_reparking import reconcile_confirmed_video_reparking


class LiveReparkingEvidence:
    """Accumulate image-time, per-vehicle evidence, without sharing any state with video replay.

    The temporary stall machine is *evidence only*. Its estimated 'available'
    must NEVER be used for the live guide, because live empty-space validation
    is stricter and independently managed by SpaceObserver.
    """

    def __init__(self, zones):
        # Legacy bottom-footprint geometry for live safety. No wheel guesses,
        # and no mask-only region assignment without a separate verification.
        self.machine = RecordedParkingStateMachine(
            zones, geometry_mode="legacy",
            initially_confirmed_empty_uids=[],
        )

    def update(self, tracker, detections, zones, inside, now):
        # The recorded-video evidence state uses an elapsed monotonic timestamp.
        # Here now is the LIVE monotonic clock, not frame index / video time.
        self.machine.update(detections, zones, inside, now)
        # A second object in the same stall, including an unverified detection,
        # prevents claiming the stall for a single re-parked vehicle.
        ambiguous = set()
        for d in detections:
            tid = d.get("track_id")
            if tid is None or d.get("monitored") is False:
                continue
            for uid in set(d.get("zone_touched") or ()):
                ambiguous.add((uid, int(tid)))
            if d.get("zone_candidate"):
                ambiguous.add((d["zone_candidate"], int(tid)))

        eligible = []
        for d in detections:
            tid = d.get("track_id")
            uid = d.get("demo_zone")
            if tid is None or not uid:
                eligible.append(d)
                continue
            conflicts = {
                other_tid for zone, other_tid in ambiguous
                if zone == uid and other_tid != int(tid)
            }
            if conflicts:
                # Do not mutate the actual recorded-zone candidate or
                # monitored/verified flags; only suppress re-parking evidence.
                eligible.append({**d, "demo_stopped": False})
            else:
                eligible.append(d)

        events = reconcile_confirmed_video_reparking(
            tracker, self.machine, eligible, now)
        # The reconciliation function modifies the copied detection when a
        # candidate was suppressed. Ensure callers get the confirmed marker.
        for d, candidate in zip(detections, eligible):
            if candidate is not d and candidate.get("repark_confirmed_by_recorded_stall"):
                d.update({
                    "confirmed_parked_space": candidate["confirmed_parked_space"],
                    "repark_confirmed_by_recorded_stall": True,
                })
        return events
