"""Regression cases from 2026-10-29: missing tyre, noisy boxes, wrong stall.

No live camera or Supabase connection is needed.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from monitor import Vehicle, VehicleTracker, classify_spaces, inside
from parking_diagnostics import ParkingDiagnosticRecorder


class TemporalParkingTest(unittest.TestCase):
    def setUp(self):
        self.zones = {
            "space_001": [[0.00, .2], [.49, .2], [.49, 1], [0, 1]],
            "space_002": [[.50, .2], [1, .2], [1, 1], [.50, 1]],
        }

    def test_stopped_car_with_intermittent_zone_still_parks(self):
        tracker = VehicleTracker("home-test-001", "test", park_seconds=5)
        for step in range(28):
            now = step * .5
            uid = "space_001" if step % 4 != 0 else None
            position = (.22 + (step % 3 - 1) * .003, .65)
            d = {"track_id": 17, "point": position, "zone_candidate": uid}
            tracker.update([d], self.zones, [], now)
        record = tracker.vehicles[17]
        self.assertEqual(record.phase, "parked")
        self.assertEqual(record.space_uid, "space_001")
        self.assertTrue(d["stationary"])
        self.assertEqual(d["zone_smoothed"], "space_001")

    def test_no_zone_votes_no_park_even_if_still(self):
        tracker = VehicleTracker("home-test-001", "test", park_seconds=3)
        for step in range(30):
            tracker.update([{"track_id": 1, "point": (.2, .65),
                             "zone_candidate": None}],
                           self.zones, [], step * .5)
        self.assertNotEqual(tracker.vehicles[1].phase, "parked")

    def test_driving_through_stall_does_not_park(self):
        tracker = VehicleTracker("home-test-001", "test", park_seconds=3)
        for step in range(22):
            x = .12 + step * .015
            tracker.update([{"track_id": 9, "point": (x, .65),
                             "zone_candidate": "space_001"}],
                           self.zones, [], step * .5)
        self.assertNotEqual(tracker.vehicles[9].phase, "parked")

    def test_parked_vehicle_is_not_exiting_from_missing_zone(self):
        car = Vehicle("test", "home-test-001", 1, phase="parked",
                      space_uid="space_001", park_anchor=(.25, .75))
        for step in range(20):
            car.observe((.25 + (step % 2) * .004, .75),
                        None, False, step * .5, 5)
        self.assertEqual(car.phase, "parked")

    def test_real_movement_can_mark_exiting_after_2_seconds(self):
        car = Vehicle("test", "home-test-001", 1, phase="parked",
                      space_uid="space_001", park_anchor=(.15, .75))
        for step in range(25):
            car.observe((.15 + step * .014, .75),
                        None, False, step * .5, 5)
        self.assertEqual(car.phase, "exiting")

    def test_parked_car_does_not_claim_neighbor_is_available(self):
        car = {"track_id": 22, "point": (.48, .75),
               "wheel_points": [],
               "zone_candidate": "space_001",
               "zone_touched": ["space_001", "space_002"],
               "confirmed_parked_space": "space_001"}
        result = classify_spaces([car], [], self.zones, parked_track_ids={22})
        self.assertEqual(result["space_001"], "occupied")
        self.assertEqual(result["space_002"], "unknown")

    def test_wheel_body_conflict_must_not_reconfirm_parked(self):
        tracker = VehicleTracker("home-test-001", "test", park_seconds=3)
        tracker.vehicles[7] = Vehicle("test", "home-test-001", 7,
                                      phase="parked", space_uid="space_001",
                                      park_anchor=(.25, .75))
        d = {"track_id": 7, "point": (.25, .75),
             "zone_candidate": None, "zone_basis": "conflict",
             "zone_touched": ["space_001", "space_002"],
             "wheel_points": []}
        tracker.update([d], self.zones, [], 10)
        self.assertIsNone(d["confirmed_parked_space"])

    def test_diagnostic_csv_has_stall_reason_without_images(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = ParkingDiagnosticRecorder(directory)
            recorder.write([{"track_id": 1, "phase": "moving",
                             "point": (.2, .65), "confidence": .8,
                             "zone_candidate": None, "zone_votes": 0,
                             "zone_basis": "uncertain", "stationary": False}],
                           self.zones, {"space_001": "unknown"}, 0)
            recorder.close()
            with (Path(directory) / "駐車区画_判定診断.csv").open(
                    "r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["追跡ID"], "1")
            self.assertIn("ZONE_UNKNOWN", rows[0]["注意事項"])


if __name__ == "__main__":
    unittest.main()
