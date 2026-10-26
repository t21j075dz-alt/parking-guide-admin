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
        observer = SpaceObserver(["space_001"], allow_initial_empty=True)
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
        # 最初から区画内にある車は本当の駐車開始を測定できない
        self.assertIsNone(tracker.vehicles[7].parked_at)

    def test_departure_can_confirm_vacancy_without_false_free(self):
        observer = SpaceObserver(["space_001"], absence_hold_seconds=3)
        observer.update({"space_001": "occupied"}, 0)
        observer.update({"space_001": "occupied"}, 1)
        self.assertEqual(observer.update({"space_001": "available"}, 2)["space_001"], "occupied")
        self.assertEqual(observer.update({"space_001": "available"}, 5)["space_001"], "occupied")
        self.assertEqual(observer.update({"space_001": "available"}, 5.5)["space_001"], "unknown")
        observer.update({"space_001": "available"}, 6, departures=["space_001"])
        self.assertNotEqual(observer.update({"space_001": "available"}, 7)["space_001"], "available")
        self.assertEqual(observer.update({"space_001": "available"}, 12)["space_001"], "available")

    def test_no_initial_free_without_verification(self):
        observer = SpaceObserver(["space_001"])
        for now in (0, 1, 10, 20):
            self.assertEqual(observer.update({"space_001": "available"}, now)["space_001"], "unknown")

    def test_border_straddling_car_cannot_make_adjacent_free(self):
        from monitor import classify_spaces
        zones = {"A": [[0, 0],[.5,0],[.5,1],[0,1]],
                 "B": [[.5,0],[1,0],[1,1],[.5,1]]}
        car = [{"point": (.495,.7), "bottom_points": [(.45,.7),(.495,.7),(.56,.7)]}]
        states = classify_spaces(car, [], zones)
        self.assertNotEqual(states["A"], "available")
        self.assertNotEqual(states["B"], "available")

    def test_track_lost_is_not_exit(self):
        tracker = VehicleTracker("home-test-001", "camera", lost_seconds=3)
        tracker.update([{"track_id": 2, "point": (0.8, 0.8)}], self.zones, [], 1)
        events = tracker.update([], self.zones, [], 5)
        self.assertTrue(any(e["phase"] == "lost" for e in events))
        self.assertFalse(any(e["phase"] == "exited" for e in events))


if __name__ == "__main__":
    unittest.main()
