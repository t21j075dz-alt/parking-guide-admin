"""Real-time recorded-video demo safety and timing (no camera, network or GPU)."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prepare_video_demo import make_video_config, DEMO_FACILITY
from video_demo_support import (
    VIDEO_FACILITY, SOURCE, require_demo_mode,
    parse_verified_empty, demo_status_rows, set_demo_visibility,
)
from video_replay import VideoReplay, validate_video
from transfer_home_zones import source_zones


def notebook():
    ids = [f"space_{n:03d}" for n in range(1, 7)]
    return {
        "facility_id": "home-test-001",
        "space_uids": ids,
        "space_zones": {
            uid: [[.01*i, .1], [.01*i+.005, .1],
                  [.01*i+.005, .16], [.01*i, .16]]
            for i, uid in enumerate(ids, 1)
        },
        "camera_kind": None,
        "calibration_capture": {"source": "1", "kind": "usb",
                                "width": 1280, "height": 720},
        "entry_zone": [], "exit_zone": [],
    }


def desktop():
    return {
        "facility_id": "home-test-001",
        "camera_id": "home-camera-01",
        "source": 0, "vehicle_model": r"C:\desktop\my-best.pt",
        "supabase_url": "https://example.supabase.co",
        "publishable_key": "dummy-publishable-key",
        "camera_verified_external": True,
        "camera_kind": "camo",
        "camera_capture_width": 0, "camera_capture_height": 0,
        "space_uids": ["space_001"], "space_zones": {},
        "allow_unverified_initial_empty": False,
        "initially_confirmed_empty_uids": ["space_001"],
        "initial_empty_verified_at": "2026-10-28T00:00:00+00:00",
    }


class DemoConfigTests(unittest.TestCase):
    def test_isolated_config_keeps_desktop_model_and_cloud_but_six_zones(self):
        original = desktop()
        config = make_video_config(original, notebook())
        self.assertEqual(config["facility_id"], VIDEO_FACILITY)
        self.assertEqual(config["space_uids"], notebook()["space_uids"])
        self.assertEqual(len(config["space_zones"]), 6)
        self.assertEqual(config["camera_id"], "home-video-demo-camera")
        self.assertEqual(config["vehicle_model"], original["vehicle_model"])
        self.assertEqual(config["publishable_key"], original["publishable_key"])
        self.assertEqual(config["camera_kind"], "usb")
        self.assertEqual(config["calibration_capture"]["source"], "0")
        self.assertEqual(config["camera_verified_external"], False)
        self.assertFalse(config["allow_unverified_initial_empty"])
        self.assertEqual(config["initially_confirmed_empty_uids"], [])
        self.assertNotIn("initial_empty_verified_at", config)
        self.assertEqual(original["facility_id"], "home-test-001")
        self.assertEqual(original["space_zones"], {})

    def test_recorded_video_must_not_publish_to_real_home_facility(self):
        args = SimpleNamespace(video="sample.mp4", demo_publish=True)
        with self.assertRaisesRegex(ValueError, "専用"):
            require_demo_mode(desktop(), args)
        config = make_video_config(desktop(), notebook())
        require_demo_mode(config, args)
        with self.assertRaisesRegex(ValueError, "実カメラ"):
            require_demo_mode(config, SimpleNamespace(video="", demo_publish=False))
        with self.assertRaisesRegex(ValueError, "--video"):
            require_demo_mode(config, SimpleNamespace(video="", demo_publish=True))

    def test_verified_empty_cannot_be_fabricated_or_duplicate(self):
        ids, zones = source_zones(notebook())
        self.assertEqual(parse_verified_empty("space_001,space_006", zones),
                         ["space_001", "space_006"])
        self.assertEqual(parse_verified_empty("", zones), [])
        with self.assertRaises(ValueError):
            parse_verified_empty("space_001,space_001", zones)
        with self.assertRaises(ValueError):
            parse_verified_empty("space_999", zones)

    def test_demo_status_rows_are_isolated_and_labeled(self):
        settings = make_video_config(desktop(), notebook())
        rows = demo_status_rows(settings, {"space_001": "occupied"},
                                "2026-10-29T00:00:00+00:00",
                                {"space_001": "stopped"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["facility_id"], DEMO_FACILITY)
        self.assertEqual(rows[0]["source"], SOURCE)
        self.assertEqual(rows[0]["status"], "occupied")
        self.assertEqual(rows[0]["occupancy_phase"], "stopped")
        with self.assertRaisesRegex(ValueError, "一致していません"):
            demo_status_rows(settings, {"space_001": "available"},
                             "2026-10-29T00:00:00+00:00",
                             {"space_001": "stopped"})
        with self.assertRaises(ValueError):
            demo_status_rows(desktop(), {"space_001": "available"}, "now")

    def test_visibility_only_updates_separate_demo_facility(self):
        class FakeWriter:
            def __init__(self):
                self.url = "https://example.supabase.co"
                self.key = "publishable-key"
                self.access_token = "user-jwt"
                self.calls = 0
            def _ensure_token(self):
                self.calls += 1

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'[{"facility_id":"home-video-demo-001","is_published":true}]'

        writer = FakeWriter()
        def fake_open(req, timeout=10):
            self.assertEqual(req.method, "PATCH")
            self.assertIn("facility_id=eq.home-video-demo-001", req.full_url)
            self.assertNotIn("home-test-001", req.full_url)
            self.assertEqual(req.get_header("Authorization"), "Bearer user-jwt")
            return Response()

        with patch("video_demo_support.request.urlopen", fake_open):
            set_demo_visibility(writer, True)
        self.assertEqual(writer.calls, 1)


class FakeFrame:
    def copy(self):
        return FakeFrame()


class FakeCapture:
    def __init__(self):
        self.index = 0
        self.frames = [FakeFrame() for _ in range(90)]
        self.is_open = True
    def isOpened(self):
        return self.is_open
    def read(self):
        if self.index >= len(self.frames):
            return False, None
        result = self.frames[self.index]
        self.index += 1
        return True, result
    def get(self, prop):
        return {5: 30.0, 7: 90}.get(prop, 0)
    def set(self, prop, value):
        self.index = int(value)
        return True
    def grab(self):
        if self.index >= len(self.frames):
            return False
        self.index += 1
        return True
    def release(self):
        self.is_open = False


class FakeCV2:
    CAP_PROP_FPS = 5
    CAP_PROP_FRAME_COUNT = 7
    CAP_PROP_POS_FRAMES = 1
    def __init__(self):
        self.cap = FakeCapture()
    def VideoCapture(self, path):
        return self.cap


class VideoReplayTests(unittest.TestCase):
    def test_real_time_video_skips_late_frames_and_reaches_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            path.write_bytes(b"placeholder for fake decoder")
            clock = [100.0]
            sleep_calls = []
            cv2 = FakeCV2()
            replay = VideoReplay(path, cv2, root=Path(directory) / "logs",
                                 clock=lambda: clock[0],
                                 sleeper=lambda seconds: sleep_calls.append(seconds))
            replay.start()
            first, seq = replay.next_frame(0)
            self.assertEqual(seq, 1)
            clock[0] += 0.7
            frame, seq = replay.next_frame(seq)
            self.assertEqual(seq, 22)  # The actual video frame #21 at .7 seconds.
            self.assertEqual(replay.frame_index, 21)
            self.assertTrue(frame is not None)
            replay.log_status({"space_001": "unknown"})
            self.assertTrue((replay.folder / "区画状態の変化.csv").is_file())
            clock[0] += 5
            frame, seq = replay.next_frame(seq)
            self.assertIsNone(frame)
            replay.close()

    def test_confirmation_does_not_skip_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(b"test")
            clock = [100.0]
            replay = VideoReplay(path, FakeCV2(), root=Path(directory) / "logs",
                                 clock=lambda: clock[0], sleeper=lambda _: None)
            replay.start()
            clock[0] = 999.0
            replay.reset_clock_after_confirmation()
            self.assertIsNotNone(replay.next_frame(0)[0])
            self.assertEqual(replay.next_frame(1)[1], 2)
            replay.close()

    def test_reject_unexpected_file_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "MP4"):
                validate_video(path)


if __name__ == "__main__":
    unittest.main()
