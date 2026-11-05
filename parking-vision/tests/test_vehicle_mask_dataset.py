"""Offline checks for YOLO polygon data and independent video partitions."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

from annotate_vehicle_masks import polygon_to_yolo, yolo_to_polygon
from compare_vehicle_segmentation import extract_segmentation_metrics
from train_vehicle_segmentation import training_kwargs
from vehicle_mask_dataset import (
    TARGET_CLASSES, COCO_NAMES, validate_label, inspect_session,
    build_dataset,
)


LABEL = "2 0.10 0.10 0.90 0.10 0.90 0.90 0.10 0.90\n"


def make_session(folder, video_hash, *, image=b"fake jpeg", label=LABEL):
    folder.mkdir(parents=True)
    (folder / "frame_001.jpg").write_bytes(image)
    (folder / "labels").mkdir()
    (folder / "labels" / "frame_001.txt").write_text(label, encoding="utf-8")
    with (folder / "annotation_manifest.csv").open(
            "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["video_seconds", "frame_index", "image",
                         "source_video_sha256"])
        writer.writerow(["1.000", "5", "frame_001.jpg", video_hash])


class VehicleMaskDatasetTests(unittest.TestCase):
    def test_stable_coco80_indices_for_comparable_metrics(self):
        self.assertEqual(len(COCO_NAMES), 80)
        self.assertEqual({COCO_NAMES[i] for i in TARGET_CLASSES},
                         {"car", "motorcycle", "bus", "truck"})
        self.assertEqual(COCO_NAMES[2], "car")

    def test_polygons_not_detection_boxes(self):
        self.assertEqual(validate_label(LABEL), 1)
        for value in [
            "2 0.5 0.5 0.3 0.3",  # detection bbox only
            "2 0 0 1 1 0",  # malformed odd point
            "0 0 0 .5 0 .5 .5",  # unsupported class
            "2 0 0 1 0 0 NaN",
            "2 0 0 1 0 0 1.2",
            "2 0 0 0 0 0 0",
        ]:
            with self.subTest(label=value), self.assertRaises(ValueError):
                validate_label(value)
        self.assertEqual(validate_label(""), 0)  # Explicit negative image.

    def test_clicks_export_correct_normalized_polygon(self):
        line = polygon_to_yolo(
            2, [(10, 20), (80, 20), (80, 60)], 100, 100)
        self.assertEqual(validate_label(line), 1)
        kind, points = yolo_to_polygon(line, 100, 100)
        self.assertEqual(kind, 2)
        self.assertEqual(points, [(10,20),(80,20),(80,60)])

    def test_requires_annotated_original_session_metadata(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp) / "session"
            make_session(folder, "a" * 64)
            self.assertEqual(len(inspect_session(folder)[1]), 1)
            (folder / "labels" / "frame_001.txt").unlink()
            with self.assertRaisesRegex(ValueError, "未確認・未ラベル"):
                inspect_session(folder)

    def test_cannot_mix_same_raw_video_between_train_val(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_session(root/"a", "1"*64, image=b"video-a-frame1")
            make_session(root/"b", "1"*64, image=b"video-a-frame2")
            with self.assertRaisesRegex(ValueError, "同一の元動画"):
                build_dataset(root/"a", root/"b", None, root/"dataset")

    def test_rejects_duplicate_images_even_across_different_videos(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_session(root/"a", "1"*64)
            make_session(root/"b", "2"*64)
            with self.assertRaisesRegex(ValueError, "同じ画像"):
                build_dataset(root/"a", root/"b", None, root/"dataset")

    def test_builds_separate_train_val_test_and_manifest(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_session(root/"a", "1"*64, image=b"train_image")
            make_session(root/"b", "2"*64, image=b"val_image")
            make_session(root/"c", "3"*64, image=b"test_image")
            yaml, stats = build_dataset(
                root/"a", root/"b", root/"c", root/"output")
            self.assertTrue(yaml.is_file())
            self.assertEqual(stats["train"]["polygons"], 1)
            self.assertTrue((root/"output/labels/test/frame_001.txt").is_file())
            self.assertIn("test: images/test", yaml.read_text(encoding="utf-8"))
            self.assertIn("  7: \"truck\"", yaml.read_text(encoding="utf-8"))

    def test_never_overwrites_existing_dataset_output(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            make_session(root/"a", "1"*64, image=b"train")
            make_session(root/"b", "2"*64, image=b"val")
            (root/"out").mkdir()
            (root/"out"/"keep.txt").write_text("do not overwrite")
            with self.assertRaisesRegex(ValueError, "既存ファイル"):
                build_dataset(root/"a", root/"b", None, root/"out")
            self.assertEqual((root/"out"/"keep.txt").read_text(), "do not overwrite")

    def test_training_arguments_safely_choose_new_output(self):
        with TemporaryDirectory() as temp:
            yaml = Path(temp)/"dataset.yaml"
            yaml.write_text("x: test")
            opts = training_kwargs(yaml, epochs=50, device="auto")
            self.assertEqual(opts["epochs"], 50)
            self.assertEqual(opts["workers"], 0)
            self.assertIsNone(opts["device"])
            self.assertFalse(opts["exist_ok"])

    def test_extract_metrics_keeps_true_mask_map_distinct_from_box(self):
        metrics = SimpleNamespace(
            seg=SimpleNamespace(map=.41,map50=.76,map75=.35),
            box=SimpleNamespace(map=.86))
        parsed = extract_segmentation_metrics(metrics)
        self.assertEqual(parsed["mask_map50_95"], .41)
        self.assertEqual(parsed["box_map50_95"], .86)


if __name__ == "__main__":
    unittest.main()
