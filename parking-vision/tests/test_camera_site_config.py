"""カメラ敷地マスク・死角・管理アプリUIDの設定検証。"""
import json
from pathlib import Path
import tempfile
import unittest

from monitor import inside, load_config


class CameraSiteConfigTest(unittest.TestCase):
    def base_config(self):
        return {
            "facility_id": "home-test-001", "camera_id": "cam",
            "source": 0, "supabase_url": "https://example.supabase.co",
            "publishable_key": "public-key",
            "space_zones": {"space_001":[[.1,.1],[.4,.1],[.4,.4],[.1,.4]]},
            "monitored_site_polygon":[[0,0],[.5,0],[.5,.5],[0,.5]],
            "camera_blind_space_uids": ["space_001"],
            "occluded_by_spaces":{},
        }

    def load(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(contents), encoding="utf-8")
            return load_config(str(path))

    def test_camera_site_polygon_limits_background_road(self):
        config = self.load(self.base_config())
        self.assertTrue(inside((.2,.2), config["monitored_site_polygon"]))
        self.assertFalse(inside((.8,.8), config["monitored_site_polygon"]))

    def test_invalid_blind_space_rejected(self):
        conf = self.base_config()
        conf["camera_blind_space_uids"]=["not_registered"]
        with self.assertRaisesRegex(ValueError, "camera_blind"):
            self.load(conf)

    def test_invalid_occlusion_relation_rejected(self):
        conf = self.base_config()
        conf["occluded_by_spaces"]={"space_001":["not_registered"]}
        with self.assertRaisesRegex(ValueError, "occluded_by_spaces"):
            self.load(conf)

    def test_legacy_config_remains_compatible(self):
        conf = self.base_config()
        conf.pop("monitored_site_polygon")
        conf.pop("camera_blind_space_uids")
        conf.pop("occluded_by_spaces")
        self.assertEqual(self.load(conf)["facility_id"],"home-test-001")


if __name__ == "__main__":
    unittest.main()
