"""Automatic vehicle detect conversion uses verified segmentation only."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from derive_vehicle_detection_dataset import polygon_to_box, prepare

CAR1 = "2 0.10 0.20 0.40 0.20 0.40 0.60 0.10 0.60\n"
CAR2 = "7 0.45 0.55 0.75 0.55 0.75 0.85 0.45 0.85\n"


def create_src(folder):
    (folder / "images" / "train").mkdir(parents=True)
    (folder / "labels" / "train").mkdir(parents=True)
    label_counts = [2, 0, 1]
    for index, count in enumerate(label_counts):
        stem = f"photo_{index:03d}"
        (folder / "images" / "train" / (stem + ".jpeg")).write_bytes(bytes([index + 2]))
        (folder / "labels" / "train" / (stem + ".txt")).write_text(
            [CAR1 + CAR2, "", CAR1][index], encoding="utf-8")
    (folder / "dataset_summary.json").write_text(json.dumps({
        "task": "vehicle", "independent_validation": False,
        "splits": {"train": {"images": 3, "objects": 3}}
    }), encoding="utf-8")


class DerivedVehicleDetectionTests(unittest.TestCase):
    def test_pure_conversion_preserves_coco_class_id_and_box_geometry(self):
        fields = polygon_to_box(CAR1.strip()).split()
        self.assertEqual(fields[0], "2")
        self.assertEqual([float(v) for v in fields[1:]], [.25, .4, .3, .4])
        with self.assertRaises(ValueError):
            polygon_to_box("2 0.5 0.5 0.2 0.2")

    def test_provenance_and_no_new_labels(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            src = root / "src"
            create_src(src)
            out = root / "new"
            yaml, stats = prepare(src, out)
            self.assertEqual(stats["train"], {"images": 3, "objects": 3})
            self.assertEqual(
                len(list((out / "images" / "train").glob("*.jpeg"))), 3)
            self.assertEqual(
                len((out / "labels" / "train" / "photo_001.txt").read_text()), 0)
            self.assertEqual(
                len((out / "labels" / "train" / "photo_000.txt").read_text().splitlines()), 2)
            meta = json.loads((out / "dataset_summary.json").read_text())
            self.assertTrue(meta["derived_from_reviewed_vehicle_polygons"])
            self.assertFalse(meta["independent_validation"])
            self.assertIn("  2: \"car\"", yaml.read_text())
            self.assertEqual((src / "labels" / "train" / "photo_000.txt").read_text(),
                             CAR1 + CAR2)
            with self.assertRaisesRegex(ValueError, "上書き"):
                prepare(src, out)

    def test_rejects_incomplete_labels_or_task_mismatch(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            src = root / "src"
            create_src(src)
            summary = src / "dataset_summary.json"
            data = json.loads(summary.read_text())
            data["task"] = "obstacle"
            summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "車体輪郭"):
                prepare(src, root / "out")
            data["task"] = "vehicle"
            summary.write_text(json.dumps(data))
            (src / "labels" / "train" / "photo_000.txt").unlink()
            with self.assertRaisesRegex(ValueError, "正解ラベル"):
                prepare(src, root / "out")

    def test_rejects_changed_counts_and_mismatched_splits(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            src = root / "src"
            create_src(src)
            summary = src / "dataset_summary.json"
            data = json.loads(summary.read_text())
            data["splits"]["train"]["objects"] = 90
            summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "個数"):
                prepare(src, root / "out")


if __name__ == "__main__":
    unittest.main()
