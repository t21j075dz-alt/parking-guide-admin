"""Offline tests: a one-frame YOLO experiment does not claim real validation."""
import csv
import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from first_frame_pilot import prepare_seg, prepare_obstacles, train_pilot

POLYGON = "2 0.10 0.10 0.90 0.10 0.90 0.90 0.10 0.90\n"


def make_session(root, first_label=POLYGON):
    session = root / "nikko_01"
    session.mkdir()
    (session / "labels").mkdir()
    rows = []
    for index, label in enumerate((first_label, POLYGON)):
        name = f"frame_{index:08d}_{index:.2f}s.jpg"
        (session / name).write_bytes(b"image " + str(index).encode())
        (session / "labels" / (Path(name).stem + ".txt")).write_text(label)
        rows.append((str(index), str(index * 30), name, "a" * 64))
    with (session / "annotation_manifest.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("video_seconds", "frame_index", "image", "source_video_sha256"))
        writer.writerows(rows)
    return session


class FirstFramePilotTests(unittest.TestCase):
    def test_prepares_only_first_frame_without_claiming_validation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root, POLYGON * 50)
            yaml, count = prepare_seg(session, root / "seg_data")
            self.assertEqual(count, 50)
            self.assertEqual(len(list((yaml.parent / "images" / "train").glob("*.jpg"))), 1)
            self.assertEqual(len(list((yaml.parent / "labels" / "train").glob("*.txt"))), 1)
            self.assertIn("val: images/train", yaml.read_text())
            self.assertIn('  2: "car"', yaml.read_text())
            self.assertFalse(json.loads(
                (yaml.parent / "pilot_metadata.json").read_text())["independent_validation"])

    def test_will_not_replace_existing_dataset(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root)
            destination = root / "existing"
            destination.mkdir()
            (destination / "keep").write_text("safe")
            with self.assertRaisesRegex(ValueError, "上書き"):
                prepare_seg(session, destination)
            self.assertEqual((destination / "keep").read_text(), "safe")

    def test_rejects_empty_vehicle_label(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root, "")
            with self.assertRaisesRegex(ValueError, "輪郭"):
                prepare_seg(session, root / "out")

    def test_obstacle_photo_does_not_reuse_car_polygon(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root)
            output = root / "obstacles"
            image = prepare_obstacles(session, output)
            self.assertTrue(image.is_file())
            self.assertFalse((output / "labels").exists())
            self.assertEqual(len(list(output.glob("*.jpg"))), 1)

    def test_output_cannot_be_inside_session(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root)
            with self.assertRaises(ValueError):
                prepare_seg(session, session / "nested")

    def test_train_disables_validation_and_overwrite(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            session = make_session(root)
            yaml, _ = prepare_seg(session, root / "output")
            options = []
            class FakeYOLO:
                task = "segment"
                trainer = types.SimpleNamespace(save_dir="test-run")
                def __init__(self, path):
                    self.path = path
                def train(self, **kwargs):
                    options.append(kwargs)
            with patch.dict(sys.modules, {"ultralytics": types.SimpleNamespace(YOLO=FakeYOLO)}):
                train_pilot(yaml, model_path="fake-seg.pt", epochs=3, device="cpu")
            self.assertEqual(len(options), 1)
            self.assertFalse(options[0]["val"])
            self.assertFalse(options[0]["exist_ok"])
            self.assertEqual(options[0]["batch"], 1)
            self.assertEqual(options[0]["mosaic"], 0.0)


if __name__ == "__main__":
    unittest.main()
