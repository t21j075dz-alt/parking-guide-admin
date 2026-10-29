"""A short, successful YOLO raw-ID handoff must be recorded even between samples."""
from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from parking_diagnostics import ParkingDiagnosticRecorder


class ParkingDiagnosticHandoffTests(unittest.TestCase):
    def test_one_frame_car_handoff_is_always_logged(self):
        with tempfile.TemporaryDirectory() as tempdir:
            recorder = ParkingDiagnosticRecorder(tempdir, interval_seconds=2.)
            zones = {"space_003": [[.3,.3],[.6,.3],[.6,.7],[.3,.7]]}
            status = {"space_003": "occupied"}
            base = {
                "name": "car",
                "track_id": 1,
                "raw_track_id": 1,
                "confidence": .9,
                "stationary": False,
                "bbox": [481,385,741,545],
                "id_reassociated": False,
            }
            recorder.write([base], zones, status, 594.0, video_seconds=594.0)
            # This event would previously be lost: only 0.4 seconds after
            # the ordinary sample and true for just one YOLO frame.
            handoff = {**base, "raw_track_id": 42,
                       "id_reassociated": True,
                       "bbox": [705,507,1176,719]}
            recorder.write([handoff], zones, status, 594.4, video_seconds=594.4)
            no_repeat = {**handoff, "id_reassociated": False}
            recorder.write([no_repeat], zones, status, 594.6, video_seconds=594.6)
            recorder.close()
            with (Path(tempdir) / "駐車区画_判定診断.csv").open(
                    encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["YOLO生ID"], "1")
            self.assertEqual(rows[1]["YOLO生ID"], "42")
            self.assertEqual(rows[1]["安定車両ID"], "1")
            self.assertEqual(rows[1]["ID引継ぎ"], "YES")
            self.assertEqual(rows[1]["録画経過秒"], "594.4")

    def test_unassociated_video_frames_stay_interval_sampled(self):
        with tempfile.TemporaryDirectory() as tempdir:
            recorder = ParkingDiagnosticRecorder(tempdir, interval_seconds=2.)
            zones = {"space_001": []}
            recorder.write([], zones, {"space_001":"available"}, 0.)
            recorder.write([], zones, {"space_001":"available"}, .4)
            recorder.write([], zones, {"space_001":"available"}, 2.1)
            recorder.close()
            with (Path(tempdir) / "駐車区画_判定診断.csv").open(
                    encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
