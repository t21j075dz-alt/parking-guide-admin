"""Test safe batch-training plan and dataset checks without GPU."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from auto_train_all import check_source, commands, prepare_derived
from derive_vehicle_detection_dataset import prepare


class AutoTrainAllTests(unittest.TestCase):
    def test_three_sequential_commands_are_separated_and_nonlive(self):
        steps = commands(epochs=5, imgsz=640, batch=1, device="cpu")
        self.assertEqual([task for task, _ in steps],
                         ["vehicle", "obstacle", "vehicle_detect"])
        for task, args in steps:
            self.assertIn("--accept-train-only", args)
            self.assertIn("--auto-augment", args)
            self.assertEqual(args[args.index("--task") + 1], task)
            self.assertEqual(args[args.index("--device") + 1], "cpu")
            self.assertNotIn("--resume", args)
            self.assertNotIn("config.json", " ".join(args))
        self.assertEqual(
            steps[0][1][steps[0][1].index("--auto-augment") + 1], "lighting")
        with self.assertRaises(ValueError):
            commands(epochs=0)

    def test_refuse_nonreviewed_or_empty_data(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "dataset.yaml").write_text("train: images/train\n")
            summary = root / "dataset_summary.json"
            summary.write_text(json.dumps({
                "task": "vehicle", "independent_validation": False,
                "splits": {"train": {"images": 241, "objects": 893}}
            }))
            self.assertEqual(check_source(root, "vehicle")["splits"]["train"]["images"], 241)
            with self.assertRaisesRegex(ValueError, "教師データ"):
                check_source(root, "obstacle")
            summary.write_text(json.dumps({
                "task": "vehicle", "independent_validation": True,
                "splits": {"train": {"images": 241, "objects": 893}}
            }))
            with self.assertRaisesRegex(ValueError, "独立val"):
                check_source(root, "vehicle")


if __name__ == "__main__":
    unittest.main()
