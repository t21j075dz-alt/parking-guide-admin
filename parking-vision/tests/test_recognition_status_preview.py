"""No image data or GPU required to test safe model selection and sampling."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from recognition_status_preview import (
    current_weight, find_weight, model_paths, source_photos, spread_indices
)


class RecognitionPreviewTests(unittest.TestCase):
    def test_detects_only_existing_local_weights(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertIsNone(find_weight("vehicle_mask", root))
            self.assertIsNone(find_weight("obstacle", root))
            self.assertIsNone(current_weight(root))
            file = (root / "runs" / "unified_training" /
                    "vehicle_lighting_auto_v1" / "weights" / "last.pt")
            file.parent.mkdir(parents=True)
            file.write_bytes(b"model")
            self.assertEqual(find_weight("vehicle_mask", root), file)
            self.assertIsNone(find_weight("vehicle_box", root))
            (root / "config.json").write_text(json.dumps({
                "vehicle_model": "missing_best.pt",
                "publishable_key": "not-reported"
            }))
            self.assertIsNone(current_weight(root))
            model = root / "previous_best.pt"
            model.write_bytes(b"model")
            (root / "config.json").write_text(json.dumps({
                "vehicle_model": "previous_best.pt"
            }))
            self.assertEqual(current_weight(root), model)
            result = model_paths(root, {})
            self.assertEqual(result["current"], model)
            self.assertEqual(result["vehicle_mask"], file)
            self.assertIsNone(result["obstacle"])

    def test_images_sample_evenly_without_touching_source(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(241):
                (root / f"photo_{index:04d}.jpeg").write_bytes(bytes([index % 256]))
            photos = source_photos(root, 12)
            self.assertEqual(len(photos), 12)
            self.assertEqual(photos[0].name, "photo_0000.jpeg")
            self.assertEqual(photos[-1].name, "photo_0240.jpeg")
            self.assertEqual(len(list(root.iterdir())), 241)

    def test_sample_indices_and_bad_weight_override(self):
        self.assertEqual(spread_indices(3, 12), [0, 1, 2])
        self.assertEqual(spread_indices(241, 1), [0])
        self.assertEqual(len(spread_indices(241, 12)), 12)
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "モデル"):
                model_paths(Path(temp), {"obstacle": Path(temp) / "nonexistent.pt"})


if __name__ == "__main__":
    unittest.main()
