# -*- coding: utf-8 -*-
"""Check segmentation settings without downloading models or requiring a GPU."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from segmentation_quality import (
    resolve_segmentation_settings, infer_segments,
)
from vehicle_segmentation import SegmentationDiagnosticRecorder


class RecorderModel:
    def __init__(self):
        self.calls = []

    def track(self, frame, **kwargs):
        self.calls.append(("track", frame, kwargs))
        return ["tracked"]

    def predict(self, frame, **kwargs):
        self.calls.append(("predict", frame, kwargs))
        return ["predicted"]


class SegmentationQualityTests(unittest.TestCase):
    def test_old_independent_preview_retains_previous_defaults(self):
        conf = resolve_segmentation_settings("auto", tracking=False)
        self.assertEqual((conf.quality, conf.model, conf.imgsz,
                          conf.retina_masks),
                         ("standard", "yolo11n-seg.pt", 640, False))

    def test_tracking_defaults_to_high_quality(self):
        conf = resolve_segmentation_settings("auto", tracking=True)
        self.assertEqual((conf.quality, conf.model, conf.imgsz,
                          conf.retina_masks),
                         ("high", "yolo11s-seg.pt", 960, True))

    def test_explicit_standard_reproduces_previous_tracking(self):
        conf = resolve_segmentation_settings("standard", tracking=True)
        self.assertEqual(conf.model, "yolo11n-seg.pt")
        self.assertEqual(conf.imgsz, 640)
        self.assertFalse(conf.retina_masks)

    def test_maximum_and_custom_overrides(self):
        maximum = resolve_segmentation_settings("maximum", tracking=True)
        self.assertEqual(maximum.model, "yolo11m-seg.pt")
        self.assertEqual(maximum.imgsz, 1280)
        self.assertTrue(maximum.retina_masks)
        custom = resolve_segmentation_settings(
            "high", model=r"C:\trained\best-seg.pt", imgsz=1024,
            tracking=True)
        self.assertEqual(custom.model, r"C:\trained\best-seg.pt")
        self.assertEqual(custom.imgsz, 1024)
        self.assertTrue(custom.retina_masks)

    def test_invalid_quality_or_size_rejected(self):
        with self.assertRaises(ValueError):
            resolve_segmentation_settings("extreme", tracking=True)
        for value in (-10, 128, 2048):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_segmentation_settings("high", imgsz=value)

    def test_tracking_passes_retina_masks_with_existing_tracker_arguments(self):
        model = RecorderModel()
        conf = resolve_segmentation_settings("high", tracking=True)
        self.assertEqual(infer_segments(
            model, "frame", conf, tracking=True,
            tracker_file="botsort-parking.yaml", confidence=.1), ["tracked"])
        kind, frame, args = model.calls[0]
        self.assertEqual((kind, frame), ("track", "frame"))
        self.assertEqual(args["imgsz"], 960)
        self.assertTrue(args["retina_masks"])
        self.assertTrue(args["persist"])
        self.assertEqual(args["tracker"], "botsort-parking.yaml")
        self.assertEqual(args["conf"], .1)

    def test_preview_has_no_tracking_side_effects(self):
        model = RecorderModel()
        conf = resolve_segmentation_settings("standard", tracking=False)
        self.assertEqual(infer_segments(
            model, "frame", conf, confidence=.35), ["predicted"])
        self.assertEqual(model.calls[0][0], "predict")
        self.assertFalse(model.calls[0][2]["retina_masks"])
        self.assertNotIn("persist", model.calls[0][2])

    def test_high_quality_experiment_metadata_is_saved_in_csv(self):
        settings = resolve_segmentation_settings("high", tracking=True)
        with TemporaryDirectory() as folder:
            recorder = SegmentationDiagnosticRecorder(folder, settings=settings)
            recorder.write([{
                "track_id": 1,
                "segmentation_contour": [(0,0),(1,0),(1,1)],
                "segmentation_confidence": .95,
                "segmentation_match_iou": .90,
            }], 175.0)
            recorder.close()
            with (Path(folder)/"車両輪郭_比較診断.csv").open(
                    encoding="utf-8-sig", newline="") as input_file:
                rows = list(csv.DictReader(input_file))
            row = rows[0]
            self.assertEqual(row["quality_preset"], "high")
            self.assertEqual(row["model_name"], "yolo11s-seg.pt")
            self.assertEqual(row["input_imgsz"], "960")
            self.assertEqual(row["high_resolution_masks"], "yes")
            self.assertEqual(row["contour_vertices"], "3")


if __name__ == "__main__":
    unittest.main()
