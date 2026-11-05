"""Opt-in YOLO instance-segmentation comparison: no GPU or model downloads."""
import csv
from pathlib import Path
import tempfile
import unittest

from monitor import classify_spaces, inside
from vehicle_segmentation import (
    SegmentationDiagnosticRecorder, attach_vehicle_contours, box_iou,
    draw_vehicle_contours, estimate_mask_zone, lower_silhouette_points,
)


class FakeTensor:
    def __init__(self, data):
        self.data = data

    def cpu(self):
        return self

    def int(self):
        return self

    def tolist(self):
        return self.data


class FakeBoxes:
    def __init__(self, boxes, classes, confidences):
        self.xyxy = FakeTensor(boxes)
        self.cls = FakeTensor(classes)
        self.conf = FakeTensor(confidences)


class FakeMasks:
    def __init__(self, polygons):
        self.xy = polygons


class FakeResult:
    def __init__(self, boxes, classes, confidences, polygons, names=None):
        self.boxes = FakeBoxes(boxes, classes, confidences)
        self.masks = FakeMasks(polygons) if polygons is not None else None
        self.names = names or {2: "car", 3: "motorcycle"}


class SegmentationTests(unittest.TestCase):
    def setUp(self):
        self.zones = {
            "space_001": [[0, 0], [.65, 0], [.65, 1], [0, 1]],
            "space_002": [[.65, 0], [1, 0], [1, 1], [.65, 1]],
        }
        self.polygon = [(20, 30), (70, 30), (80, 60), (75, 75),
                        (25, 75), (20, 60)]
        self.result = FakeResult([[20, 20, 80, 80]], [2], [.91],
                                 [self.polygon])

    def test_mask_matches_original_track_with_lower_silhouette(self):
        detection = {"name": "car", "bbox": [20, 20, 80, 80],
                     "track_id": 5, "zone_candidate": "space_002",
                     "point": (.5, .8), "image_size": (100, 100)}
        matched = attach_vehicle_contours([detection], self.result,
                                          (100, 100, 3), self.zones, inside)
        self.assertEqual(matched, 1)
        self.assertEqual(detection["track_id"], 5)
        self.assertEqual(detection["zone_candidate"], "space_002")
        self.assertGreaterEqual(len(detection["segmentation_bottom_points"]), 5)
        self.assertEqual(detection["segmentation_match_iou"], 1.0)
        self.assertTrue(detection["segmentation_contour"])
        # Neither the diagnostic mask candidate nor its contour may modify
        # the original occupied-space logic.
        raw = classify_spaces([detection], [], self.zones, parked_track_ids={5})
        self.assertEqual(raw["space_002"], "occupied")
        self.assertEqual(raw["space_001"], "available")

    def test_one_mask_cannot_be_assigned_to_two_tracks(self):
        detections = [
            {"name": "car", "bbox": [20, 20, 80, 80]},
            {"name": "car", "bbox": [18, 18, 82, 82]},
        ]
        count = attach_vehicle_contours(detections, self.result, (100, 100, 3))
        self.assertEqual(count, 1)
        self.assertEqual(sum(bool(d.get("segmentation_contour")) for d in detections), 1)
        self.assertTrue(detections[0].get("segmentation_contour"))

    def test_wrong_class_and_distant_detection_are_not_matched(self):
        wrong_class = [{"name": "motorcycle", "bbox": [20, 20, 80, 80]}]
        self.assertEqual(attach_vehicle_contours(
            wrong_class, self.result, (100, 100, 3)), 0)
        distant = [{"name": "car", "bbox": [0, 0, 10, 10]}]
        self.assertEqual(attach_vehicle_contours(
            distant, self.result, (100, 100, 3)), 0)
        self.assertEqual(box_iou([0, 0, 10, 10], [20, 20, 80, 80]), 0)

    def test_missing_masks_safely_falls_back_to_original(self):
        result = FakeResult([[20, 20, 80, 80]], [2], [.93], None)
        detection = [{"name": "car", "bbox": [20, 20, 80, 80]}]
        self.assertEqual(attach_vehicle_contours(
            detection, result, (100, 100, 3)), 0)
        self.assertNotIn("segmentation_contour", detection[0])

    def test_diagonal_lower_boundary_varies_and_is_not_box_bottom(self):
        polygon = [(10, 10), (80, 10), (80, 80), (10, 50)]
        points = lower_silhouette_points(polygon, (100, 100, 3))
        self.assertEqual(len(points), 9)
        self.assertLess(points[0][1], points[-1][1])
        self.assertLess(points[0][1], .80)

    def test_ambiguous_zone_stays_undecided(self):
        zones = {
            "left": [[0, 0], [.5, 0], [.5, 1], [0, 1]],
            "right": [[.5, 0], [1, 0], [1, 1], [.5, 1]],
        }
        points = [((i + .5) / 10, .80) for i in range(10)]
        zone, touched = estimate_mask_zone(points, zones, inside)
        self.assertIsNone(zone)
        self.assertEqual(touched, {"left", "right"})

    def test_draws_on_copy_not_camera_frame(self):
        import numpy as np
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        detection = {"segmentation_contour": self.polygon,
                     "segmentation_bottom_points": [(0.5, .75)]}
        drawn = draw_vehicle_contours(frame, [detection])
        self.assertFalse(frame.any())
        self.assertTrue(drawn.any())

    def test_csv_contains_only_anonymous_numeric_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            writer = SegmentationDiagnosticRecorder(folder)
            writer.write([{"track_id": 8, "raw_track_id": 99,
                           "zone_candidate": "space_001",
                           "segmentation_candidate": "space_002",
                           "segmentation_contour": self.polygon,
                           "segmentation_bottom_points": [(0.5, .75)]}], 12.5)
            writer.close()
            with (Path(folder) / "車両輪郭_比較診断.csv").open(
                    encoding="utf-8-sig", newline="") as stream:
                data = list(csv.DictReader(stream))
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["match_state"], "matched")
            self.assertEqual(data[0]["legacy_zone"], "space_001")
            self.assertEqual(data[0]["segmentation_zone"], "space_002")
            self.assertEqual(data[0]["video_seconds"], "12.500")


if __name__ == "__main__":
    unittest.main()
