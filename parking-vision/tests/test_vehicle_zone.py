"""Tests for image-based zone estimates and stationary-only occupation."""
import unittest

from monitor import VehicleTracker, classify_spaces, inside
from vehicle_zone import annotate_vehicle_zones, locate_vehicle_zone


class CameraZoneTests(unittest.TestCase):
    def setUp(self):
        # Neighboring left/right parking spaces, as seen from a fixed camera.
        self.zones = {
            "space_001": [[0, .35], [.5, .35], [.5, .98], [0, .98]],
            "space_003": [[.5, .35], [1, .35], [1, .98], [.5, .98]],
        }

    def test_missing_wheels_can_use_lower_body_when_single_zone(self):
        det = {"track_id": 11, "name": "car", "confidence": .9,
               "point": (.24, .74), "bbox": [30, 20, 170, 160],
               "bottom_points": [(.24, .8)], "wheel_points": []}
        annotate_vehicle_zones([det], self.zones, inside, (200, 400, 3))
        self.assertEqual(det["zone_candidate"], "space_001")
        self.assertEqual(det["zone_basis"], "bottom-footprint")
        self.assertEqual(classify_spaces([det], [], self.zones, parked_track_ids=set())["space_001"], "unknown")
        self.assertEqual(classify_spaces([det], [], self.zones, parked_track_ids={11})["space_001"], "occupied")

    def test_straddled_lower_body_remains_uncertain(self):
        det = {"track_id": 11, "point": (.5, .75),
               "bbox": [120, 30, 280, 180], "wheel_points": []}
        uid, touched, basis = locate_vehicle_zone({**det, "image_size": (400, 200)}, self.zones, inside)
        self.assertIsNone(uid)
        self.assertGreaterEqual(len(touched), 2)

    def test_tracker_can_park_using_estimated_zone_not_wheel(self):
        tracker = VehicleTracker("home-test-001", "cam1", park_seconds=5)
        det = {"track_id": 7, "point": (.26, .77),
               "zone_candidate": "space_001"}
        for t in range(0, 10):
            tracker.update([det], self.zones, [], float(t))
        self.assertEqual(tracker.vehicles[7].phase, "parked")
        self.assertEqual(tracker.vehicles[7].space_uid, "space_001")


if __name__ == "__main__":
    unittest.main()
