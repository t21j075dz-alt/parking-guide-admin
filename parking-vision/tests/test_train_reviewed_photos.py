"""No GPU tests: do not pretend train-only scores are a valid evaluation."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from train_reviewed_photos import prepare_options


class ReviewedTrainingArgumentsTests(unittest.TestCase):
    def prepare(self, folder, task="vehicle", has_val=False):
        folder.mkdir()
        (folder / "dataset.yaml").write_text("train: images/train\n")
        (folder / "dataset_summary.json").write_text(json.dumps({
            "task": task,
            "independent_validation": has_val,
            "splits": {"train": {"images": 242, "objects": 389},
                       "val": {"images": 40, "objects": 20} if has_val else {}}
        }))
        return folder / "dataset.yaml"

    def test_single_session_requires_explicit_opt_in_and_no_validation(self):
        with TemporaryDirectory() as d:
            path = self.prepare(Path(d) / "dataset")
            with self.assertRaisesRegex(ValueError, "独立した検証"):
                prepare_options(path, "vehicle")
            options, has_val = prepare_options(
                path, "vehicle", accept_train_only=True)
            self.assertFalse(has_val)
            self.assertFalse(options["val"])
            self.assertFalse(options["exist_ok"])
            self.assertEqual(options["workers"], 0)
            self.assertEqual(options["batch"], 2)

    def test_independent_validation_enables_metrics(self):
        with TemporaryDirectory() as d:
            path = self.prepare(Path(d) / "dataset", "obstacle", True)
            options, has_val = prepare_options(path, "obstacle")
            self.assertTrue(has_val)
            self.assertTrue(options["val"])
            self.assertTrue(options["plots"])

    def test_model_type_and_dataset_task_cannot_be_mixed(self):
        with TemporaryDirectory() as d:
            path = self.prepare(Path(d) / "dataset", "vehicle", True)
            with self.assertRaisesRegex(ValueError, "一致しません"):
                prepare_options(path, "obstacle")

    def test_reject_bad_parameters_and_no_positive_labels(self):
        with TemporaryDirectory() as d:
            path = self.prepare(Path(d) / "dataset", "vehicle", True)
            for kwargs in ({"epochs": 0}, {"imgsz": 200}, {"batch": 0},
                           {"name": "../overwrite"}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    prepare_options(path, "vehicle", **kwargs)
            metadata = json.loads((path.parent / "dataset_summary.json").read_text())
            metadata["splits"]["train"]["objects"] = 0
            (path.parent / "dataset_summary.json").write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "正解ラベル"):
                prepare_options(path, "vehicle")


if __name__ == "__main__":
    unittest.main()
