"""通信・学習モデルなしで検証できる区画と追跡の単体テスト。"""
import unittest
from monitor import VehicleTracker, SpaceObserver, inside, space_for


class ParkingLogicTest(unittest.TestCase):
    def setUp(self):
        self.zones = {"space_001": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]}

    def test_point_in_polygon(self):
        self.assertTrue(inside((0.25, 0.25), self.zones["space_001"]))
        self.assertFalse(inside((0.75, 0.75), self.zones["space_001"]))
        self.assertEqual(space_for((0.25, 0.25), self.zones), "space_001")

    def test_free_requires_five_seconds(self):
        observer = SpaceObserver(["space_001"])
        observer.update({"space_001": "available"}, 1)
        self.assertEqual(observer.update({"space_001": "available"}, 2)["space_001"], "unknown")
        self.assertEqual(observer.update({"space_001": "available"}, 6)["space_001"], "available")

    def test_car_before_parked(self):
        tracker = VehicleTracker("home-test-001", "camera", park_seconds=5)
        for clock in range(1, 12):
            events = tracker.update(
                [{"track_id": 7, "point": (0.25, 0.25)}],
                self.zones, [], float(clock))
        self.assertEqual(tracker.vehicles[7].phase, "parked")
        self.assertEqual(tracker.vehicles[7].space_uid, "space_001")
        self.assertTrue(tracker.vehicles[7].parked_at)

    def test_track_lost_is_not_exit(self):
        tracker = VehicleTracker("home-test-001", "camera")
        tracker.update([{"track_id": 2, "point": (0.8, 0.8)}], self.zones, [], 1)
        events = tracker.update([], self.zones, [], 5)
        self.assertTrue(any(e["phase"] == "lost" for e in events))
        self.assertFalse(any(e["phase"] == "exited" for e in events))


if __name__ == "__main__":
    unittest.main()
