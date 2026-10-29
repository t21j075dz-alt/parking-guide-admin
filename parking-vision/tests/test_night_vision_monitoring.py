"""Regressions from the 17:45-17:53 nighttime experimental recordings.

The cameras showed many low-light car boxes beyond the six calibrated zones.
Those detections should not become parking sessions or occupied states.
"""
import unittest

from monitor import inside, classify_spaces, VehicleTracker
from night_vision import inference_frame
from vehicle_zone import annotate_vehicle_zones, is_monitored_vehicle


class NightCameraMonitoringTest(unittest.TestCase):
    def setUp(self):
        self.zones = {
            "space_001": [[.16,.55],[.38,.55],[.38,.8],[.16,.8]],
            "space_003": [[.39,.55],[.61,.55],[.61,.8],[.39,.8]],
        }

    def test_background_car_does_not_create_live_parking_track(self):
        far = {"track_id": 44, "name": "car",
               "confidence": .94, "point": (.78,.31),
               "bbox": [850, 90, 1050, 220], "wheel_points": []}
        annotate_vehicle_zones([far], self.zones, inside, (720, 1280, 3))
        self.assertFalse(is_monitored_vehicle(far, self.zones, inside))
        tracker = VehicleTracker("home-test-001", "test", park_seconds=3)
        for t in range(15):
            candidates = [far] if is_monitored_vehicle(far, self.zones, inside) else []
            tracker.update(candidates, self.zones, [], t)
        self.assertEqual(len(tracker.vehicles), 0)
        self.assertNotEqual(classify_spaces([], [], self.zones)["space_003"], "occupied")

    def test_near_stall_vehicle_is_not_ignored(self):
        car = {"track_id": 8, "name": "car", "confidence": .85,
               "point": (.48,.70), "bbox": [540, 380, 720, 535],
               "wheel_points": []}
        annotate_vehicle_zones([car], self.zones, inside, (720, 1280, 3))
        self.assertTrue(is_monitored_vehicle(car, self.zones, inside))

    def test_unrelated_road_vehicle_does_not_revoke_approved_empty(self):
        car = {"point": (.95,.2), "bbox": [1100,40,1250,120],
               "wheel_points": [], "confidence": .9}
        annotate_vehicle_zones([car], self.zones, inside, (720, 1280, 3))
        self.assertFalse(is_monitored_vehicle(car, self.zones, inside))
        states = classify_spaces([], [], self.zones, parked_track_ids=set())
        self.assertEqual(states["space_001"], "available")

    def test_night_enhancement_preserves_dimensions_and_bright_frames(self):
        import numpy as np
        dark = np.full((120, 160, 3), 20, dtype=np.uint8)
        filtered, applied, brightness = inference_frame(dark)
        self.assertFalse(applied)  # Near-black: do not amplify sensor noise
        self.assertIs(filtered, dark)
        self.assertEqual(filtered.shape, dark.shape)
        self.assertLess(brightness, 35)
        moderate = np.full((120, 160, 3), 45, dtype=np.uint8)
        moderate_result, applied, _ = inference_frame(moderate)
        self.assertTrue(applied)  # Moderate low light: cautious CLAHE
        self.assertEqual(moderate_result.shape, moderate.shape)
        bright = np.full((120, 160, 3), 170, dtype=np.uint8)
        clean, applied, _ = inference_frame(bright)
        self.assertFalse(applied)
        self.assertIs(clean, bright)
        self.assertTrue((dark == 20).all())  # Camera source must stay unchanged.


if __name__ == "__main__":
    unittest.main()
