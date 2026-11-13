"""日光の駐車枠なしYOLOプレビュー：クラウド・実カメラを使わない純粋機能の回帰。"""
import json
from pathlib import Path
import tempfile
import unittest

from preview_nikko_no_zones import (
    count_frame, detection_category, read_model_settings, validate_source,
)


class DetectionOnlyTests(unittest.TestCase):
    def test_counts_detected_objects_without_any_parking_zone(self):
        vehicles = [
            {"name": "car", "confidence": 0.95, "bbox": [5, 6, 20, 21], "track_id": 1},
            {"name": "truck", "confidence": 0.71, "bbox": [15, 16, 30, 31], "track_id": 2},
            {"name": "bicycle", "confidence": 0.78, "bbox": [35, 36, 50, 51], "track_id": 3},
        ]
        blockers = [
            {"name": "person", "confidence": 0.68, "bbox": [40, 40, 55, 55]},
            {"name": "traffic_cone", "confidence": 0.66, "bbox": [10, 12, 20, 25]},
        ]
        self.assertEqual(count_frame(vehicles, blockers), {
            "vehicles": 2, "bikes": 1, "people": 1, "obstacles": 1,
        })
        self.assertEqual(detection_category("motorcycle"), "bikes")
        self.assertEqual(detection_category("pedestrian"), "people")
        self.assertEqual(detection_category("shopping_cart"), "obstacles")

    def test_reads_existing_model_configuration_but_not_parking_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            model = folder / "best.pt"
            model.write_bytes(b"test placeholder")
            (folder / "config.json").write_text(json.dumps({
                "vehicle_model": "best.pt",
                "tracking_confidence": .16,
                "image_size": 960,
                "space_zones": {"space_001": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                "supabase_url": "https://example.invalid",
            }))
            config = read_model_settings(folder / "config.json")
            self.assertEqual(config["model"], str(model.resolve()))
            self.assertEqual(config["confidence"], .16)
            self.assertNotIn("space_zones", config)
            self.assertNotIn("supabase_url", config)
            config = read_model_settings(folder / "no-config.json", explicit_model=str(model))
            self.assertEqual(config["model"], str(model.resolve()))
            with self.assertRaisesRegex(ValueError, "見つかりません"):
                read_model_settings(folder / "no-config.json", explicit_model="missing.pt")

    def test_rejects_processed_or_unavailable_video_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            video = folder / "raw.mp4"
            video.write_bytes(b"video sample")
            self.assertEqual(validate_source(video), video.resolve())
            processed = folder / "YOLO判定_123.mp4"
            processed.write_bytes(b"video sample")
            with self.assertRaisesRegex(ValueError, "元の撮影映像"):
                validate_source(processed)
            with self.assertRaisesRegex(ValueError, "動画"):
                validate_source(folder / "notfound.mp4")


if __name__ == "__main__":
    unittest.main()
