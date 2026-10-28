"""カメラ画角チェックのテスト。実機カメラがなくても実行できる。"""
import unittest
from camera_profiles import fit_preview_dimensions, capture_preferences, assert_calibrated_view

class TestCameraProfiles(unittest.TestCase):
    def test_fit_wide(self):
        self.assertEqual((1280, 720), fit_preview_dimensions(1920, 1080, 1280, 800))

    def test_fit_portrait(self):
        self.assertEqual((450, 800), fit_preview_dimensions(1080, 1920, 1280, 800))

    def test_fit_4by3(self):
        self.assertEqual((1067, 800), fit_preview_dimensions(1600, 1200, 1280, 800))

    def test_native_setting(self):
        self.assertEqual((0, 0, 0), capture_preferences({}))

    def test_half_resolution_rejected(self):
        with self.assertRaises(ValueError):
            capture_preferences({"camera_capture_width": 1920})

    def test_camo_requires_calibration(self):
        with self.assertRaises(ValueError):
            assert_calibrated_view({"camera_kind":"camo","source":1}, 1920,1080)

    def test_camera_mismatch(self):
        s={"camera_kind":"camo","source":1,"calibration_capture":{
             "kind":"camo","source":"1","width":1280,"height":720}}
        assert_calibrated_view(s,1920,1080) # 同じ縦横比なら可
        with self.assertRaises(ValueError):
            assert_calibrated_view(s,1280,960) # 縦横比が異なる
        s["source"]=2
        with self.assertRaises(ValueError):
            assert_calibrated_view(s,1920,1080)

if __name__ == "__main__":
    unittest.main()
