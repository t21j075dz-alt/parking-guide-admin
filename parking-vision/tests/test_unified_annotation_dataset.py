"""Test the unified annotation workspace without GUI, GPU or live camera."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from unified_annotation_dataset import (
    AnnotationWorkspace, export_dataset, validate_task_label, image_id,
)

VEHICLE = "2 0.10 0.10 0.90 0.10 0.90 0.90 0.10 0.90\n"
OBSTACLE = "0 0.50 0.50 0.30 0.40\n"


def setup_workspace(root, name="train", amount=2):
    images = root / (name + "_photos")
    images.mkdir()
    for i in range(amount):
        (images / f"IMG_{i:04d}.jpeg").write_bytes(f"frame {name} {i}".encode())
    ws = AnnotationWorkspace(images, root / (name + "_workspace"))
    return ws


class UnifiedDatasetTests(unittest.TestCase):
    def test_independent_tasks_and_reviewed_empty_labels(self):
        with TemporaryDirectory() as temp:
            ws = setup_workspace(Path(temp))
            photo = ws.photos[0]
            self.assertFalse(ws.is_reviewed(photo, "vehicle"))
            self.assertFalse(ws.is_reviewed(photo, "obstacle"))
            ws.save(photo, "vehicle", VEHICLE)
            ws.save(photo, "obstacle", "")
            self.assertTrue(ws.is_reviewed(photo, "vehicle"))
            self.assertTrue(ws.is_reviewed(photo, "obstacle"))
            self.assertEqual(ws.progress(), {"vehicle": 1, "obstacle": 1, "layout": 0})
            self.assertNotEqual(ws.label_path(photo, "vehicle"),
                                ws.label_path(photo, "obstacle"))
            self.assertEqual(ws.read(photo, "vehicle")[0], VEHICLE)
            self.assertEqual(ws.read(photo, "obstacle")[0], "")
            ws2 = AnnotationWorkspace(ws.images_root, ws.workspace)
            self.assertTrue(ws2.is_reviewed(ws2.photos[0], "obstacle"))

    def test_rejects_inference_boxes_as_segmentation_polygons(self):
        with self.assertRaises(ValueError):
            validate_task_label("vehicle", "2 .5 .5 .5 .5")
        with self.assertRaises(ValueError):
            validate_task_label("obstacle", VEHICLE)
        self.assertEqual(validate_task_label("vehicle", VEHICLE), 1)
        self.assertEqual(validate_task_label("obstacle", OBSTACLE), 1)

    def test_no_auto_export_of_unreviewed_photos(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ws = setup_workspace(root)
            ws.save(ws.photos[0], "vehicle", VEHICLE)
            with self.assertRaisesRegex(ValueError, "未確認"):
                export_dataset(ws, "vehicle", root / "out", allow_train_only=True)
            self.assertFalse((root / "out").exists())

    def test_train_only_exports_human_reviewed_photos_and_preserves_source(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ws = setup_workspace(root, amount=242)
            for i, photo in enumerate(ws.photos):
                ws.save(photo, "vehicle", VEHICLE if i == 0 else "")
                ws.save(photo, "obstacle", OBSTACLE if i == 0 else "")
            yaml, stats = export_dataset(ws, "vehicle", root / "seg_dataset",
                                         allow_train_only=True)
            self.assertEqual(stats["train"], {"images": 242, "objects": 1})
            self.assertIn('  2: "car"', yaml.read_text())
            self.assertTrue(json.loads(
                (yaml.parent / "dataset_summary.json").read_text())["training_only"])
            self.assertEqual(len(list((yaml.parent / "images/train").glob("*.jpeg"))), 242)
            self.assertEqual(len(list((yaml.parent / "labels/train").glob("*.txt"))), 242)
            self.assertEqual(len(list(ws.images_root.glob("*.jpeg"))), 242)
            yaml_obstacle, stats2 = export_dataset(ws, "obstacle", root / "obs_dataset",
                                                    allow_train_only=True)
            self.assertEqual(stats2["train"]["images"], 242)
            self.assertIn('  0: "traffic_cone"', yaml_obstacle.read_text())
            self.assertNotIn('  2: "car"', yaml_obstacle.read_text())

    def test_val_requires_distinct_folder_and_no_duplicate_images(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            train = setup_workspace(root, "train")
            val = setup_workspace(root, "val")
            for ws in (train, val):
                for p in ws.photos:
                    ws.save(p, "vehicle", VEHICLE)
            yaml, stats = export_dataset(train, "vehicle", root / "dataset",
                                         val_workspace=val)
            self.assertEqual(stats["val"]["images"], 2)
            self.assertTrue(json.loads(
                (yaml.parent / "dataset_summary.json").read_text())["independent_validation"])
            with self.assertRaisesRegex(ValueError, "上書き"):
                export_dataset(train, "vehicle", root / "dataset", val_workspace=val)
            val.photos[0]["path"].write_bytes(train.photos[0]["path"].read_bytes())
            with self.assertRaisesRegex(ValueError, "重複"):
                export_dataset(train, "vehicle", root / "new", val_workspace=val)

    def test_disallows_source_replacement_and_workspace_inside_photos(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            ws = setup_workspace(root)
            other = setup_workspace(root, "other")
            with self.assertRaises(ValueError):
                AnnotationWorkspace(other.images_root, ws.workspace)
            with self.assertRaises(ValueError):
                AnnotationWorkspace(ws.images_root, ws.images_root / "out")

    def test_unique_ids_for_same_names_in_different_subfolders(self):
        self.assertNotEqual(image_id(Path("a/photo.jpg")),
                            image_id(Path("b/photo.jpg")))


if __name__ == "__main__":
    unittest.main()
