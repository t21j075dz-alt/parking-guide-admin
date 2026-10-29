"""Nighttime false-car regression scenarios: static objects vs real arrivals."""
import unittest

from monitor import VehicleTracker, classify_spaces
from night_vehicle_evidence import NightVehicleEvidenceGate


class NightCarEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.zones = {
            "space_003": [[.08,.10],[.80,.10],[.80,.95],[.08,.95]],
        }

    def test_static_headlight_reflection_must_not_be_called_a_car(self):
        gate = NightVehicleEvidenceGate()
        tracker = VehicleTracker("home-test-001", "camera", park_seconds=3)
        for i in range(32):
            now = i * .5
            det = {"track_id": 7,
                   "point": (.4 + (i % 3 - 1) * .003, .5),
                   "confidence": .97,
                   "zone_candidate": "space_003",
                   "zone_touched": ["space_003"],
                   "zone_nearby": ["space_003"],
                   "wheel_points": []}
            gate.update([det], now, low_light=True)
            self.assertFalse(det["night_verified"])
            validated = [det] if det["night_verified"] else []
            tracker.update(validated, self.zones, [], now)
            raw = classify_spaces([det], [], self.zones,
                                  parked_track_ids=set())
            self.assertEqual(raw["space_003"], "unknown")
        self.assertEqual(len(tracker.vehicles), 0)

    def test_real_car_moving_then_stopping_can_be_parked_at_night(self):
        gate = NightVehicleEvidenceGate()
        tracker = VehicleTracker("home-test-001", "camera", park_seconds=3)
        verified = False
        for i in range(42):
            now = i * .5
            x = .15 + min(i, 14) * .012
            det = {"track_id": 5,
                   "point": (x, .50),
                   "confidence": .88,
                   "zone_candidate": "space_003",
                   "zone_touched": ["space_003"],
                   "zone_nearby": ["space_003"],
                   "wheel_points": []}
            gate.update([det], now, low_light=True)
            verified = verified or det["night_verified"]
            candidates = [det] if det["night_verified"] else []
            tracker.update(candidates, self.zones, [], now)
        self.assertTrue(verified)
        self.assertEqual(tracker.vehicles[5].phase, "parked")
        self.assertEqual(tracker.vehicles[5].space_uid, "space_003")
        classified = classify_spaces([det], [], self.zones, parked_track_ids={5})
        self.assertEqual(classified["space_003"], "occupied")

    def test_single_jitter_jump_cannot_validate_ghost_car(self):
        gate = NightVehicleEvidenceGate()
        for i in range(20):
            x = .25 if i < 10 else .45
            det = {"track_id": 1, "point": (x, .50)}
            gate.update([det], i * .5, low_light=True)
            self.assertFalse(det["night_verified"])

    def test_stale_id_must_reverify(self):
        gate = NightVehicleEvidenceGate(lifetime_seconds=3)
        for i in range(10):
            det = {"track_id": 5, "point": (.1 + .02 * i, .5)}
            gate.update([det], i * .5, low_light=True)
        self.assertTrue(det["night_verified"])
        det = {"track_id": 5, "point": (.32, .5)}
        gate.update([det], 9.0, low_light=True)
        self.assertFalse(det["night_verified"])

    def test_daylight_and_untracked_night(self):
        gate = NightVehicleEvidenceGate()
        bright = {"track_id": 3, "point": (.2, .5)}
        gate.update([bright], 0, low_light=False)
        self.assertTrue(bright["night_verified"])
        unknown_id = {"track_id": None, "point": (.2, .5)}
        gate.update([unknown_id], 1, low_light=True)
        self.assertFalse(unknown_id["night_verified"])


if __name__ == "__main__":
    unittest.main()
