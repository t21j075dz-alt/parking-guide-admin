"""YOLO判定付き動画をカメラやGPUなしで検証する。"""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from monitor import overlay
from yolo_visual_recording import YoloVisualRecorder


class Frame:
    def __init__(self, width=640, height=480, marker=""):
        self.shape = (height, width, 3)
        self.marker = marker

    def copy(self):
        return Frame(self.shape[1], self.shape[0], self.marker)


class Writer:
    def __init__(self, path, works=True):
        self.path = Path(path)
        self.works = works
        self.frames = []
        self.closed = False
        if works:
            self.path.write_bytes(b"fake video")

    def isOpened(self):
        return self.works

    def write(self, frame):
        self.frames.append(frame)

    def release(self):
        self.closed = True


class Cv2Stub:
    FONT_HERSHEY_SIMPLEX = 1
    LINE_AA = 16
    BORDER_CONSTANT = 0

    def __init__(self, works=True):
        self.videos = []
        self.boxes = []
        self.texts = []
        self.works = works

    def VideoWriter_fourcc(self, *letters):
        return 42

    def VideoWriter(self, filename, codec, fps, dimensions):
        result = Writer(filename, self.works)
        self.videos.append(result)
        return result

    def copyMakeBorder(self, frame, top, bottom, left, right, method, value):
        return Frame(frame.shape[1], frame.shape[0] + bottom)

    def rectangle(self, frame, first, second, color, thickness, antialias):
        self.boxes.append((first, second, color))

    def line(self, frame, first, second, color, thickness, antialias):
        pass

    def putText(self, frame, message, place, font, scale, color, thickness, antialias):
        self.texts.append(message)


class AnnotatedRecordingTest(unittest.TestCase):
    def test_results_written_and_manifest_contains_start_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            cv2 = Cv2Stub()
            recorder = YoloVisualRecorder(tmp, cv2, session_start=100.,
                                          fps=5)
            frame = Frame()
            recorder.write(frame, now=102.0)
            recorder.write(frame, now=103.0)
            recorder.write(frame, now=104.0)
            recorder.close()
            self.assertEqual(len(cv2.videos), 1)
            # 2 seconds => 11 frames (includes first and last time slot).
            self.assertEqual(len(cv2.videos[0].frames), 11)
            self.assertTrue(cv2.videos[0].closed)
            self.assertTrue((Path(tmp) / "YOLO判定_001.mp4").exists())
            with (Path(tmp) / "YOLO判定ファイル一覧.csv").open(
                encoding="utf-8-sig", newline=""
            ) as reader:
                index = list(csv.DictReader(reader))
            self.assertEqual(index[0]["録画開始からの秒数"], "2.000")
            self.assertEqual(index[0]["動画ファイル"], "YOLO判定_001.mp4")

    def test_no_new_inference_does_not_create_new_detection_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            cv2 = Cv2Stub()
            rec = YoloVisualRecorder(tmp, cv2, session_start=0., fps=5)
            first = Frame(width=300, marker="first")
            second = Frame(width=300, marker="second")
            rec.write(first, now=1)
            rec.write(second, now=2)
            rec.close()
            self.assertTrue(all(f.marker == "first" for f in cv2.videos[0].frames[:-1]))
            self.assertEqual(cv2.videos[0].frames[-1].marker, "second")

    def test_long_inference_gap_is_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            cv2 = Cv2Stub()
            rec = YoloVisualRecorder(tmp, cv2, session_start=0., fps=5)
            rec.write(Frame(), now=1.)
            rec.write(Frame(), now=7.)
            rec.close()
            self.assertEqual(len(cv2.videos), 2)
            self.assertTrue(cv2.videos[0].closed)
            self.assertEqual(len(cv2.videos[1].frames), 1)

    def test_annotated_video_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = YoloVisualRecorder(tmp, Cv2Stub(works=False), session_start=0.)
            with self.assertRaisesRegex(RuntimeError, "YOLO判定付き動画を保存できません"):
                rec.write(Frame(), now=1.)
            rec.close()

    def test_overlay_preserves_raw_frame_and_draws_boxes_tracking_status(self):
        fake_cv2 = Cv2Stub()
        raw = Frame(640, 480)
        detected_car = {
            "name": "car", "track_id": 15, "confidence": .82,
            "point": (.5, .5), "bbox": [110, 120, 260, 210],
        }
        person = {
            "name": "person", "track_id": None, "confidence": .76,
            "point": (.5, .5), "bbox": [270, 120, 320, 240],
        }
        zones = {"space_002": [[.1, .4], [.8, .4], [.8, .9], [.1, .9]]}
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            annotated = overlay(
                raw, zones, {"space_002": "occupied"},
                [detected_car], [person], {15: "parked"},
            )
        self.assertEqual(raw.shape, (480, 640, 3))
        self.assertEqual(annotated.shape, (578, 640, 3))
        self.assertEqual(len(fake_cv2.boxes), 2)
        written = " ".join(fake_cv2.texts)
        self.assertIn("space_002: OCCUPIED", written)
        self.assertIn("car ID15 0.82 PARKED", written)
        self.assertIn("person ID? 0.76", written)
        self.assertIn("YOLO ANALYSIS AT", written)


if __name__ == "__main__":
    unittest.main()
