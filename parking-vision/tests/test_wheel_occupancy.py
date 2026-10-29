"""Camera-zone regression tests: wheel contacts and near-car human candidates."""
import unittest

from monitor import classify_spaces, mark_vehicle_overlap, SpaceObserver


class WheelOccupancyTest(unittest.TestCase):
    def setUp(self):
        self.zones = {
            "space_001": [[0, 0], [.5, 0], [.5, 1], [0, 1]],
            "space_002": [[.5, 0], [1, 0], [1, 1], [.5, 1]],
        }

    def test_two_contacts_in_one_space_can_mark_occupied(self):
        car = {"point": (.5, .7), "bottom_points": [(.45, .7), (.55, .7)],
               "wheel_points": [(.60, .7), (.85, .7)]}
        states = classify_spaces([car], [], self.zones)
        self.assertEqual(states["space_002"], "occupied")
        self.assertNotEqual(states["space_001"], "occupied")

    def test_moving_car_wheels_do_not_claim_parked_status(self):
        car = {"track_id": 8, "point": (.70, .75),
               "bottom_points": [(.60, .8), (.80, .8)],
               "wheel_points": [(.61, .76), (.80, .76)]}
        raw = classify_spaces([car], [], self.zones, parked_track_ids=set())
        self.assertEqual(raw["space_002"], "unknown")
        parked = classify_spaces([car], [], self.zones, parked_track_ids={8})
        self.assertEqual(parked["space_002"], "occupied")

    def test_unknown_track_is_not_parked(self):
        car = {"point": (.7, .75),
               "wheel_points": [(.61, .76), (.80, .76)]}
        raw = classify_spaces([car], [], self.zones, parked_track_ids={8})
        self.assertEqual(raw["space_002"], "unknown")

    def test_clipped_car_cannot_report_wheel_contacts(self):
        import numpy as np
        from wheel_geometry import estimate_wheel_contacts
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertEqual(estimate_wheel_contacts(frame, [180, 50, 320, 180]), [])
        self.assertEqual(estimate_wheel_contacts(frame, [10, 50, 170, 240]), [])

    def test_crossing_wheel_contacts_must_not_claim_a_slot(self):
        car = {"point": (.5, .7), "bottom_points": [(.45, .7), (.55, .7)],
               "wheel_points": [(.45, .7), (.65, .7)]}
        states = classify_spaces([car], [], self.zones)
        self.assertEqual(states["space_001"], "unknown")
        self.assertEqual(states["space_002"], "unknown")

    def test_unverified_box_bottom_is_not_an_actual_tyrepair(self):
        car = {"point": (.65, .7), "bottom_points": [(.60, .8), (.70, .8)],
               "wheel_points": []}
        states = classify_spaces([car], [], self.zones)
        self.assertEqual(states["space_002"], "unknown")

    def test_person_overlap_near_vehicle_is_uncertain_not_blocked(self):
        car = {"point": (.8, .8), "bbox": [100, 100, 300, 290],
               "wheel_points": [(.60, .75), (.70, .75)]}
        person = {"point": (.40, .80), "bottom_points": [(.40, .80)],
                  "bbox": [95, 130, 135, 255], "name": "person"}
        mark_vehicle_overlap([person], [car])
        self.assertTrue(person["near_vehicle"])
        self.assertEqual(classify_spaces([car], [person], self.zones)["space_001"], "unknown")

    def test_isolated_person_remains_a_blocker_candidate(self):
        person = {"point": (.20, .8), "bottom_points": [(.20, .8)],
                  "bbox": [15, 10, 90, 180], "name": "person"}
        mark_vehicle_overlap([person], [])
        self.assertFalse(person.get("near_vehicle", False))
        self.assertEqual(classify_spaces([], [person], self.zones)["space_001"], "blocked")

    def test_short_missing_wheel_observation_keeps_known_occupancy(self):
        observer = SpaceObserver(["space_002"], absence_hold_seconds=8)
        observer.update({"space_002": "occupied"}, 0)
        self.assertEqual(observer.update({"space_002": "occupied"}, 1)["space_002"], "occupied")
        self.assertEqual(observer.update({"space_002": "unknown"}, 2)["space_002"], "occupied")
        self.assertEqual(observer.update({"space_002": "unknown"}, 4)["space_002"], "occupied")
        observer.update({"space_002": "unknown"}, 10)
        self.assertEqual(observer.update({"space_002": "unknown"}, 11)["space_002"], "unknown")

    def test_new_blocker_suspends_previously_available_space(self):
        observer = SpaceObserver(["space_001"], allow_initial_empty=True)
        observer.update({"space_001": "available"}, 0)
        self.assertEqual(observer.update({"space_001": "available"}, 6)["space_001"], "available")
        self.assertEqual(observer.update({"space_001": "blocked"}, 7)["space_001"], "unknown")
        self.assertEqual(observer.update({"space_001": "blocked"}, 8)["space_001"], "unknown")
        self.assertEqual(observer.update({"space_001": "blocked"}, 9.2)["space_001"], "blocked")

    def test_short_lived_blocker_does_not_change_published_state(self):
        observer = SpaceObserver(["space_001"], blocked_confirm_seconds=2.0)
        observer.update({"space_001": "blocked"}, 0)
        self.assertEqual(observer.update({"space_001": "blocked"}, 1)["space_001"], "unknown")
        self.assertEqual(observer.update({"space_001": "available"}, 1.5)["space_001"], "unknown")
        observer.update({"space_001": "blocked"}, 3)
        self.assertEqual(observer.update({"space_001": "blocked"}, 5.2)["space_001"], "blocked")


if __name__ == "__main__":
    unittest.main()
