"""自宅カメラ設定は元configを変えず、別施設の誤公開を防ぐ。"""
import unittest
from setup_home import prepare_home_config


class HomeSetupTest(unittest.TestCase):
    def setUp(self):
        self.base = {
            "facility_id": "home-test-001",
            "camera_id": "previous-recorded-camera",
            "source": "C:/video/test_house1.mp4",
            "vehicle_model": "C:/models/home/best.pt",
            "space_uids": ["space_001"],
            "space_zones": {"space_001": [[0, 0], [.5, 0], [.5, .5], [0, .5]]},
            "initially_confirmed_empty_uids": ["space_001"],
            "publishable_key": "local-publishable-key",
            "supabase_url": "https://example.supabase.co",
        }

    def test_safe_defaults_clear_old_camera_geometry(self):
        new = prepare_home_config(self.base, camera=0)
        self.assertEqual(new["facility_id"], "home-test-001")
        self.assertEqual(new["source"], 0)
        self.assertEqual(new["vehicle_model"], self.base["vehicle_model"])
        self.assertEqual(new["space_zones"], {})
        self.assertEqual(new["initially_confirmed_empty_uids"], [])
        self.assertFalse(new["allow_unverified_initial_empty"])
        self.assertTrue(new["verify_admin_layout_on_cloud"])
        self.assertEqual(len(self.base["space_zones"]), 1)

    def test_video_source_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_home_config(self.base, camera="recording.mp4")

    def test_nikko_cannot_be_substituted_for_home(self):
        src = dict(self.base, facility_id="nikko-test-001")
        with self.assertRaises(ValueError):
            prepare_home_config(src)

    def test_geometry_can_be_preserved_if_camera_view_is_identical(self):
        updated = prepare_home_config(self.base, reuse_camera_geometry=True)
        self.assertEqual(updated["space_zones"], self.base["space_zones"])

    def test_admin_space_uid_restricts_setup(self):
        layout = {"facilityId": "home-test-001", "objects": [
            {"objectType": "parkingSpace", "uid": "space_001"},
            {"objectType": "parkingSpace", "uid": "space_002"},
        ]}
        updated = prepare_home_config(self.base, layout=layout)
        self.assertEqual(updated["space_uids"], ["space_001", "space_002"])


if __name__ == "__main__":
    unittest.main()
