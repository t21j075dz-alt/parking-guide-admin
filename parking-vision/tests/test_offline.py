"""実カメラがなくても「USBカメラ0」「駐車時刻」「録画の結果」を検証する。"""
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from monitor import (VehicleTracker, classify_spaces, load_config,
                     detector_boxes, VEHICLE_NAMES, BLOCKING_NAMES)
from analyze_video import summarize_observations


class NextStageLogicTest(unittest.TestCase):
    def setUp(self):
        self.zone = {"space_001": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]}

    def test_zero_is_valid_camera_number(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {
                "facility_id": "home-test-001", "camera_id": "home-camera",
                "source": 0, "supabase_url": "https://example.supabase.co",
                "publishable_key": "test-public-key", "space_zones": self.zone,
            }
            filename = Path(directory) / "config.json"
            filename.write_text(json.dumps(cfg), encoding="utf-8")
            self.assertEqual(load_config(str(filename))["source"], 0)

    def test_nearby_person_blocks_empty_space(self):
        person = [{"point": (0.25, 0.25), "name": "person"}]
        self.assertEqual(classify_spaces([], person, self.zone)["space_001"], "blocked")
        car = [{"point": (0.25, 0.25), "name": "car"}]
        self.assertEqual(classify_spaces(car, person, self.zone)["space_001"], "occupied")

    def test_park_duration_starts_when_stationary_confirmed(self):
        tracker = VehicleTracker("home-test-001", "camera", park_seconds=5)
        for tick in range(1, 11):
            tracker.update(
                [{"track_id": 1, "point": (0.25, 0.25)}],
                self.zone, [], float(tick),
            )
        vehicle = tracker.vehicles[1]
        self.assertEqual(vehicle.phase, "parked")
        self.assertIsNotNone(vehicle.candidate_started_at)
        self.assertEqual(vehicle.parked_at, vehicle.candidate_started_at)

    def test_unknown_not_reported_as_accuracy(self):
        obs = {"space_001": Counter({"available": 7, "unknown": 3})}
        result = summarize_observations(obs, 10)["space_001"]
        self.assertEqual(result["available"]["share_percent"], 70.)
        self.assertEqual(result["unknown"]["frames"], 3)
        self.assertNotIn("accuracy", result)


    def test_old_visdrone_model_class_names(self):
        """2026年10月21日のモデルが出力する10種類を取りこぼさない。"""
        names = {
            0: "pedestrian", 1: "people", 2: "bicycle", 3: "car",
            4: "van", 5: "truck", 6: "tricycle", 7: "awning-tricycle",
            8: "bus", 9: "motor",
        }

        class FakeArray:
            def __init__(self, values):
                self.values = values

            def int(self):
                return self

            def cpu(self):
                return self

            def tolist(self):
                return self.values

        result = SimpleNamespace(
            names=names,
            boxes=SimpleNamespace(
                xyxy=FakeArray([[10, 10, 50, 60] for _ in names]),
                cls=FakeArray(list(names)),
                conf=FakeArray([0.9] * len(names)),
                id=FakeArray(list(names)),
            ),
        )
        vehicles = detector_boxes(result, 100, 100, VEHICLE_NAMES)
        blockers = detector_boxes(result, 100, 100, BLOCKING_NAMES)
        self.assertEqual(len(vehicles), 8)
        self.assertEqual(len(blockers), 2)
        self.assertIn("motorcycle", [row["name"] for row in vehicles])
        self.assertIn("awning_tricycle", [row["name"] for row in vehicles])
        self.assertEqual([row["name"] for row in blockers], ["person", "person"])


if __name__ == "__main__":
    unittest.main()
