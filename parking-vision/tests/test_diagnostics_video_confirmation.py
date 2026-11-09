"""Regression: diagnostic CSV must explain recorded-stop re-parks and conflicts."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from parking_diagnostics import ParkingDiagnosticRecorder


class VideoReparkingEvidenceDiagnosticsTests(unittest.TestCase):
    def test_confirmed_repark_is_logged_even_between_two_second_samples(self):
        with TemporaryDirectory() as root:
            r = ParkingDiagnosticRecorder(root, interval_seconds=2.0)
            zone = {"space_001": [[.1,.1],[.4,.1],[.4,.7],[.1,.7]]}
            states = {"space_001": "occupied"}
            car = {
                "name": "car", "track_id": 1,
                "raw_track_id": 1, "confidence": .96,
                "bbox": [100, 100, 300, 500],
                "monitored": True, "night_verified": True,
                "phase": "exiting",
                "zone_candidate": None, "zone_smoothed": None,
                "zone_basis": "ambiguous-bottom",
                "demo_geometry_basis": "mask-temporal",
            }
            r.write([car], zone, states, 494., video_seconds=494.)
            repark = {
                **car, "phase": "parked", "stationary": True,
                "demo_zone": "space_001", "demo_stopped": True,
                "confirmed_parked_space": "space_001",
                "repark_confirmed_by_recorded_stall": True,
            }
            r.write([repark], zone, states, 495., video_seconds=495.)
            # Ordinary third frame is suppressed since only 1s has passed.
            r.write([{**repark, "repark_confirmed_by_recorded_stall": False}],
                    zone, states, 495.2, video_seconds=495.2)
            r.close()
            with (Path(root) / "駐車区画_判定診断.csv").open(
                    newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["車両状態"], "exiting")
            self.assertEqual(rows[1]["車両状態"], "parked")
            self.assertEqual(rows[1]["確定駐車区画"], "space_001")
            self.assertEqual(rows[1]["駐車区画確定の根拠"], "recorded-repark")
            self.assertEqual(rows[1]["使用した区画根拠"], "mask-temporal")
            self.assertEqual(rows[1]["安定区画"], "")
            self.assertEqual(rows[1]["録画経過秒"], "495.0")

    def test_parked_state_may_be_confirmed_by_recorded_geometry(self):
        with TemporaryDirectory() as root:
            r = ParkingDiagnosticRecorder(root)
            zone = {"space_003": [[.1,.1],[.4,.1],[.4,.7],[.1,.7]]}
            car = {
                "track_id": 1, "phase": "parked",
                "demo_zone": "space_003", "demo_stopped": True,
                "demo_geometry_basis": "mask-temporal",
                "confidence": .95, "zone_smoothed": None,
                "zone_candidate": None,
            }
            r.write([car], zone, {"space_003": "occupied"}, 587.,
                    video_seconds=587.)
            r.close()
            with (Path(root) / "駐車区画_判定診断.csv").open(
                    newline="", encoding="utf-8-sig") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["確定駐車区画"], "space_003")
            self.assertEqual(row["駐車区画確定の根拠"], "recorded-stopped")
            self.assertEqual(row["使用した区画根拠"], "mask-temporal")

    def test_geometry_conflict_is_reported_not_hardcoded_as_bottom(self):
        with TemporaryDirectory() as root:
            r = ParkingDiagnosticRecorder(root)
            zone = {"space_003": [], "space_004": []}
            car = {
                "track_id": 1, "phase": "exiting",
                "demo_geometry_basis": "conflict",
                "confidence": .8,
            }
            r.write([car], zone, {"space_003": "unknown", "space_004": "unknown"},
                    174.1, video_seconds=174.1)
            r.close()
            with (Path(root) / "駐車区画_判定診断.csv").open(
                    newline="", encoding="utf-8-sig") as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row["使用した区画根拠"], "conflict")
            self.assertEqual(row["確定駐車区画"], "")


if __name__ == "__main__":
    unittest.main()
