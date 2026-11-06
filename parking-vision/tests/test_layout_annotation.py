"""Parking-layout extra labels: preserve existing reviewed vehicle/obstacle sets."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from unified_annotation_dataset import (
    AnnotationWorkspace, export_dataset, layout_polygon_to_yolo,
    layout_to_polygon, validate_layout, validate_task_label,
)

VEHICLE = "2 0.10 0.10 0.80 0.10 0.80 0.80 0.10 0.80\n"
OBSTACLE = "0 0.50 0.50 0.10 0.10\n"


def make_workspace(root):
    photos = root / "photos"
    photos.mkdir()
    for i in range(4):
        (photos / f"img_{i:02d}.jpg").write_bytes(f"original_photo_{i}".encode())
    ws = AnnotationWorkspace(photos, root / "workspace")
    for photo in ws.photos:
        ws.save(photo, "vehicle", VEHICLE)
        ws.save(photo, "obstacle", OBSTACLE)
    return ws


class LayoutAnnotationTests(unittest.TestCase):
    def test_layout_polygons_are_validated_independently(self):
        line = layout_polygon_to_yolo(0, [(0, 0), (99, 0), (99, 99), (0, 99)], 100, 100)
        self.assertEqual(validate_layout(line), 1)
        cls, points = layout_to_polygon(line, 100, 100)
        self.assertEqual(cls, 0)
        self.assertEqual(len(points), 4)
        with self.assertRaises(ValueError):
            validate_layout("0 .5 .5 .3 .3")  # box instead of polygon
        # COCO car class 2 numerically overlaps a layout class, so label paths
        # are task-separated; numeric equality does not authorize importing it.
        with self.assertRaises(ValueError):
            validate_layout("9 0.1 0.1 0.9 0.1 0.9 0.9")
        with self.assertRaises(ValueError):
            validate_layout("0 0.1 0.1 nan 0.1 0.9 0.9")
        with self.assertRaises(ValueError):
            layout_polygon_to_yolo(0, [(1, 2), (4, 5)], 100, 100)

    def test_new_layout_labels_preserve_earlier_1239_objects(self):
        with TemporaryDirectory() as d:
            ws = make_workspace(Path(d))
            before = [(ws.read(p, "vehicle")[0], ws.read(p, "obstacle")[0])
                      for p in ws.photos]
            self.assertEqual(ws.progress(), {"vehicle": 4, "obstacle": 4, "layout": 0})
            polygon = layout_polygon_to_yolo(0, [(0, 0), (20, 0), (20, 20)], 100, 100)
            ws.save(ws.photos[0], "layout", polygon + "\n")
            self.assertEqual(ws.progress()["layout"], 1)
            self.assertEqual(before, [(ws.read(p, "vehicle")[0], ws.read(p, "obstacle")[0])
                                      for p in ws.photos])
            self.assertEqual(ws.next_unreviewed(), 1)  # next unreviewed layout frame

    def test_only_reviewed_layout_export_does_not_invent_negatives(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            ws = make_workspace(root)
            mask = layout_polygon_to_yolo(0, [(0, 0), (50, 0), (50, 50)], 100, 100)
            ws.save(ws.photos[0], "layout", mask + "\n")
            ws.save(ws.photos[1], "layout", "")
            with self.assertRaisesRegex(ValueError, "未確認"):
                export_dataset(ws, "layout", root / "should_fail", allow_train_only=True)
            yaml, stats = export_dataset(
                ws, "layout", root / "layout_data",
                allow_train_only=True, reviewed_only=True)
            self.assertEqual(stats["train"], {"images": 2, "objects": 1})
            self.assertIn('0: "parking_space"', yaml.read_text())
            summary = json.loads((yaml.parent / "dataset_summary.json").read_text())
            self.assertEqual(summary["skipped_unreviewed"]["train"], 2)
            self.assertFalse(summary["independent_validation"])
            self.assertEqual(len(list((yaml.parent / "images" / "train").glob("*"))), 2)
            with self.assertRaisesRegex(ValueError, "部分書き出し"):
                export_dataset(ws, "vehicle", root / "nope",
                               allow_train_only=True, reviewed_only=True)
            with self.assertRaisesRegex(ValueError, "部分書き出し"):
                export_dataset(ws, "layout", root / "nope",
                               allow_train_only=False, reviewed_only=True)

    def test_no_layout_objects_stops_training_export(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            ws = make_workspace(root)
            ws.save(ws.photos[0], "layout", "")
            with self.assertRaisesRegex(ValueError, "正例"):
                export_dataset(ws, "layout", root / "nope",
                               allow_train_only=True, reviewed_only=True)
            self.assertFalse((root / "nope").exists())


if __name__ == "__main__":
    unittest.main()
