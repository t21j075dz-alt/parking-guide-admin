# -*- coding: utf-8 -*-
"""Real camera re-parking safety: continuous evidence, no false vacancies.

These offline tests use the actual live VehicleTracker, SpaceObserver and the
same bottom-footprint history as the video repair. No GPU, camera or Supabase.
"""
import unittest

from monitor import Vehicle, VehicleTracker, SpaceObserver, classify_spaces, inside
from reconcile_live_reparking import (
    LiveReparkingEvidence, should_enable_live_reparking,
)


ZONES = {
    "space_001": [[0.02, .2], [.44, .2], [.44, .8], [.02, .8]],
    "space_002": [[.56, .2], [.98, .2], [.98, .8], [.56, .8]],
}


def car_frame(*, tid=1, confidence=.96, verified=True, point=(.2, .48),
              zone=None, touched=None, bbox=(100, 100, 300, 500)):
    return {
        "track_id": tid, "confidence": confidence,
        "night_verified": verified, "monitored": True,
        "bbox": bbox, "image_size": (1000, 1000), "point": point,
        "zone_candidate": zone,
        "zone_touched": touched if touched is not None else ["space_001"],
    }


def exiting_tracker(previous="space_002"):
    tracker = VehicleTracker("facility", "live_camera", park_seconds=5.0)
    tracker.vehicles[1] = Vehicle(
        "live_camera", "facility", 1, phase="exiting",
        space_uid=previous, park_anchor=(.7, .5),
        left_space_at="2026-11-09T08:20:00+00:00",
    )
    return tracker


class LiveReparkingTests(unittest.TestCase):
    def test_dry_run_auto_on_publishing_explicit_opt_in(self):
        self.assertTrue(should_enable_live_reparking(
            video_mode=False, dry_run=True, config={}))
        self.assertFalse(should_enable_live_reparking(
            video_mode=False, dry_run=False, config={}))
        self.assertFalse(should_enable_live_reparking(
            video_mode=False, dry_run=False,
            config={"live_reparking_sync_enabled": "true"}))
        self.assertTrue(should_enable_live_reparking(
            video_mode=False, dry_run=False,
            config={"live_reparking_sync_enabled": True}))
        self.assertFalse(should_enable_live_reparking(
            video_mode=True, dry_run=True,
            config={"live_reparking_sync_enabled": True}))

    def test_stopped_car_with_missing_main_zone_is_reconciled_safely(self):
        tracker = exiting_tracker()
        auxiliary = LiveReparkingEvidence(ZONES)
        observer = SpaceObserver(ZONES)
        events = []
        raw_history = []
        for second in range(11):
            car = car_frame(zone=None, touched=["space_001"])
            tracker.update([car], ZONES, [], float(second))
            updates = auxiliary.update(
                tracker, [car], ZONES, inside, float(second))
            events.extend(updates)
            parked = {tid for tid, obj in tracker.vehicles.items()
                      if obj.phase == "parked"}
            raw = classify_spaces([car], [], ZONES, parked_track_ids=parked)
            statuses = observer.update(raw, float(second))
            raw_history.append(raw["space_001"])
            if second < 5:
                self.assertEqual(tracker.vehicles[1].phase, "exiting")
                self.assertNotEqual(statuses["space_001"], "occupied")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["phase"], "parked")
        self.assertEqual(events[0]["space_uid"], "space_001")
        self.assertEqual(tracker.vehicles[1].track_id, 1)
        self.assertEqual(tracker.vehicles[1].phase, "parked")
        self.assertIn("occupied", raw_history[5:])
        self.assertEqual(statuses["space_001"], "occupied")
        self.assertEqual(statuses["space_002"], "unknown")
        self.assertTrue(car["repark_confirmed_by_recorded_stall"] is False if
                        "repark_confirmed_by_recorded_stall" in car else True)

    def test_moving_pass_never_becomes_new_park(self):
        tracker = exiting_tracker()
        auxiliary = LiveReparkingEvidence(ZONES)
        events = []
        for second in range(9):
            car = car_frame(point=(.09 + .036 * second, .48),
                            bbox=(100 + 35 * second, 100,
                                  300 + 35 * second, 500),
                            zone=None, touched=["space_001"])
            tracker.update([car], ZONES, [], float(second))
            events += auxiliary.update(
                tracker, [car], ZONES, inside, float(second))
        self.assertEqual(events, [])
        self.assertEqual(tracker.vehicles[1].phase, "exiting")

    def test_unverified_or_weak_or_duplicate_vehicle_cannot_confirm(self):
        for modifier in ({"verified": False}, {"confidence": .20}):
            with self.subTest(modifier=modifier):
                tracker = exiting_tracker()
                auxiliary = LiveReparkingEvidence(ZONES)
                for second in range(10):
                    car = car_frame(**modifier)
                    tracker.update([car], ZONES, [], float(second))
                    auxiliary.update(tracker, [car], ZONES, inside,
                                     float(second))
                self.assertEqual(tracker.vehicles[1].phase, "exiting")

        tracker = exiting_tracker()
        auxiliary = LiveReparkingEvidence(ZONES)
        for second in range(10):
            car = car_frame()
            other = car_frame(tid=2, zone="space_001", touched=["space_001"])
            tracker.update([car], ZONES, [], float(second))
            events = auxiliary.update(tracker, [car, other],
                                      ZONES, inside, float(second))
            self.assertEqual(events, [])
        self.assertEqual(tracker.vehicles[1].phase, "exiting")

    def test_same_stall_return_after_real_exit_is_supported(self):
        tracker = exiting_tracker(previous="space_001")
        for second in range(13):
            d = car_frame(zone="space_001", touched=["space_001"])
            tracker.update([d], ZONES, [], float(second))
        car = tracker.vehicles[1]
        self.assertEqual(car.phase, "parked")
        self.assertEqual(car.space_uid, "space_001")


if __name__ == "__main__":
    unittest.main()
