"""Webカメラをつながずに、録画と追跡CSVの保存を検証する。"""
import csv
from pathlib import Path
import tempfile
import time
import unittest

from camera_recording import RecordingCamera, default_recording_root, open_camera


class FakeFrame:
    shape = (48, 64, 3)

    def copy(self):
        return FakeFrame()


class FakeCamera:
    def __init__(self):
        self.released = False
        self.calls = 0

    def read(self):
        time.sleep(.03)
        self.calls += 1
        if self.released:
            return False, None
        return True, FakeFrame()

    def release(self):
        self.released = True


class FakeWriter:
    def __init__(self, filename, succeeds=True):
        self.filename = Path(filename)
        self.succeeds = succeeds
        self.frames = 0
        self.closed = False
        if succeeds:
            self.filename.write_bytes(b"recording test")

    def isOpened(self):
        return self.succeeds

    def write(self, image):
        self.frames += 1

    def release(self):
        self.closed = True


class FakeCv2:
    FONT_HERSHEY_SIMPLEX = 1

    def __init__(self, succeeds=True):
        self.writers = []
        self.succeeds = succeeds

    def VideoWriter_fourcc(self, *args):
        return 1234

    def VideoWriter(self, filename, codec, fps, size):
        writer = FakeWriter(filename, succeeds=self.succeeds)
        self.writers.append(writer)
        return writer

    def putText(self, image, text, point, font, scale, color, thickness):
        pass


class RecordingTest(unittest.TestCase):
    def test_continuous_capture_and_status_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = FakeCamera()
            cv2 = FakeCv2()
            recorder = RecordingCamera(camera, cv2, root=directory,
                                       fps=10, segment_seconds=60,
                                       min_free_bytes=0)
            folder = recorder.start()
            first, number = recorder.next_frame()
            self.assertEqual(first.shape, (48, 64, 3))
            self.assertGreaterEqual(number, 1)
            time.sleep(.16)  # YOLO側が長く処理してもカメラが独立して取得する
            recorder.log_status({"space_001": "occupied", "space_002": "unknown"})
            _, next_number = recorder.next_frame(number)
            self.assertGreater(next_number, number)
            recorder.close()
            self.assertTrue((folder / "映像_001.mp4").exists())
            self.assertGreater(cv2.writers[0].frames, 0)
            self.assertTrue(cv2.writers[0].closed)
            with (folder / "区画状態の変化.csv").open(encoding="utf-8-sig") as file:
                rows = list(csv.reader(file))
            self.assertEqual(rows[1][2:], ["space_001", "occupied"])
            self.assertEqual(rows[2][2:], ["space_002", "unknown"])
            with (folder / "録画ファイル一覧.csv").open(encoding="utf-8-sig") as file:
                index = list(csv.reader(file))
            self.assertEqual(index[1][0], "映像_001.mp4")

    def test_fails_closed_when_video_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = FakeCamera()
            recorder = RecordingCamera(camera, FakeCv2(succeeds=False), root=directory,
                                       min_free_bytes=0)
            with self.assertRaisesRegex(RuntimeError, "動画を保存できません"):
                recorder.start()
            recorder.close()

    def test_recording_root_is_not_git_repo(self):
        self.assertIn("ParkingResearch", str(default_recording_root()))

    def test_minus_one_camera_is_invalid(self):
        with self.assertRaises(ValueError):
            open_camera(FakeCv2(), -1)


if __name__ == "__main__":
    unittest.main()
