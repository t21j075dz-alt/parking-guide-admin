"""日光の録画写真は明示同意・ウォーターマーク・期限付きで公開する。"""
import json
import sys
import types
import unittest
from unittest.mock import patch

from recorded_snapshots import RecordedSnapshotPublisher


class FakeWriter:
    url = "https://example.invalid"
    key = "public"
    access_token = "test"
    def __init__(self):
        self.calls = []
    def _ensure_token(self):
        return True
    def upsert(self, table, rows, keys):
        self.calls.append((table, rows, keys))


class FakeImage:
    shape = (1080, 1920, 3)
    def copy(self):
        return self


class JpegBytes(bytes):
    @property
    def nbytes(self):
        return len(self)


def fake_cv2():
    obj = types.ModuleType("cv2")
    obj.INTER_AREA = 3
    obj.FONT_HERSHEY_SIMPLEX = 1
    obj.LINE_AA = 16
    obj.IMWRITE_JPEG_QUALITY = 1
    obj.resize = lambda frame, size, interpolation: frame
    obj.rectangle = lambda *args: None
    obj.putText = lambda *args: None
    obj.imencode = lambda *args: (True, JpegBytes(b"test-jpeg"))
    return obj


class RecordedStillsTest(unittest.TestCase):
    def test_refuses_any_real_camera_or_other_facility(self):
        writer = FakeWriter()
        with self.assertRaisesRegex(ValueError, "日光"):
            RecordedSnapshotPublisher(writer, {"facility_id":"home-test-001",
                                                "camera_id":"nikko-recording-01",
                                                "video_demo_only":True})
        with self.assertRaises(ValueError):
            RecordedSnapshotPublisher(writer, {"facility_id":"nikko-test-001",
                                                "camera_id":"nikko-recording-01",
                                                "video_demo_only":True}, interval_seconds=1)

    def test_only_latest_watermarked_still_replaces_two_camera_rows(self):
        writer=FakeWriter()
        publisher=RecordedSnapshotPublisher(writer, {
            "facility_id":"nikko-test-001","camera_id":"nikko-recording-01",
            "video_demo_only":True})
        with patch.dict(sys.modules, {"cv2": fake_cv2()}):
            self.assertTrue(publisher.publish(FakeImage(), elapsed=17, cycle=2, now=10))
            self.assertFalse(publisher.publish(FakeImage(), elapsed=18, cycle=2, now=11))
        self.assertEqual(len(writer.calls), 2)
        self.assertEqual([call[0] for call in writer.calls],
                         ["parking_camera_private", "parking_camera_public"])
        self.assertTrue(writer.calls[1][1][0]["is_published"])
        self.assertTrue(writer.calls[1][1][0]["image_data"].startswith(
            "data:image/jpeg;base64,"))
        self.assertEqual(writer.calls[0][1][0]["facility_id"], "nikko-test-001")

    def test_cleanup_unpublishes_only_nikko_replay_camera(self):
        writer=FakeWriter()
        publisher=RecordedSnapshotPublisher(writer, {
            "facility_id":"nikko-test-001","camera_id":"nikko-recording-01",
            "video_demo_only":True})
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return json.dumps([{
                "facility_id":"nikko-test-001",
                "camera_id":"nikko-recording-01"}]).encode()
        with patch("recorded_snapshots.request.urlopen",return_value=Response()) as fetch:
            self.assertEqual(publisher.disable_public(),1)
            req=fetch.call_args.args[0]
            self.assertIn("nikko-test-001",req.full_url)
            self.assertIn("nikko-recording-01",req.full_url)
            self.assertEqual(req.get_method(),"PATCH")
            self.assertEqual(json.loads(req.data),{"is_published":False})


if __name__ == "__main__":
    unittest.main()
