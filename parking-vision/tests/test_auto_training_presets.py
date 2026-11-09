"""Validate automatic training presets without GPU or changing a live model."""
import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from train_reviewed_photos import main, prepare_options


class AutoTrainPresetsTests(unittest.TestCase):
    def test_auto_derived_detection_is_accepted_as_separate_task(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "dataset.yaml").write_text("train: images/train\n")
            (root / "dataset_summary.json").write_text(json.dumps({
                "task": "vehicle_detect", "independent_validation": False,
                "splits": {"train": {"images": 241, "objects": 893}}
            }))
            opts, val = prepare_options(root / "dataset.yaml", "vehicle_detect",
                                        accept_train_only=True)
            self.assertFalse(val)
            self.assertFalse(opts["val"])
            self.assertFalse(opts["exist_ok"])
            with self.assertRaisesRegex(ValueError, "一致"):
                prepare_options(root / "dataset.yaml", "obstacle",
                                accept_train_only=True)

    def test_camera_lighting_profile_is_coordinate_preserving(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            data = root / "dataset.yaml"
            data.write_text("train: images/train\n")
            (root / "dataset_summary.json").write_text(json.dumps({
                "task": "vehicle", "independent_validation": False,
                "splits": {"train": {"images": 241, "objects": 893}}
            }))
            captures = []

            class FakeYOLO:
                task = "segment"
                trainer = types.SimpleNamespace(save_dir="offline-mock")
                def __init__(self, model):
                    self.path = model
                def train(self, **kwargs):
                    captures.append(kwargs)

            argv = ["train_reviewed_photos.py", "--task", "vehicle",
                    "--data", str(data), "--device", "cpu",
                    "--accept-train-only", "--auto-augment", "lighting"]
            with patch.object(sys, "argv", argv), patch.dict(
                    sys.modules, {"ultralytics": types.SimpleNamespace(YOLO=FakeYOLO)}):
                main()
            self.assertEqual(len(captures), 1)
            opts = captures[0]
            self.assertFalse(opts["val"])
            self.assertEqual(opts["hsv_v"], .45)
            self.assertEqual(opts["scale"], 0)
            self.assertEqual(opts["mosaic"], 0)
            self.assertEqual(opts["copy_paste"], 0)
            self.assertEqual(opts["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
