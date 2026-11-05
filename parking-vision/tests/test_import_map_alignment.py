"""マップとカメラの対応付けを本番設定へ誤適用しないための回帰テスト。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from import_map_alignment import checked_alignment, prepare_settings, apply_file, main


class ImportMapAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "facility_id": "home-test-001",
            "camera_id": "home-camera-01",
            "source": 1,
            "space_uids": ["space_001", "space_002"],
            "space_zones": {},
            "supabase_url": "https://example.invalid",
            "publishable_key": "test-only",
            "camera_verified_external": True,
            "calibration_capture": {"width": 1280, "height": 720},
        }
        self.alignment = {
            "schema_version": 1,
            "facility_id": "home-test-001",
            "camera_id": "home-camera-01",
            "image_width": 640,
            "image_height": 360,
            "map_canvas": {"width": 1000, "height": 1000},
            "map_points": [[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
            "image_points": [[.15,.18],[.85,.18],[.85,.85],[.15,.85]],
            "space_uids": ["space_001", "space_002"],
            "space_zones": {
                "space_001": [[.15,.2],[.34,.2],[.34,.61],[.15,.61]],
                "space_002": [[.37,.2],[.56,.2],[.56,.61],[.37,.61]],
            },
        }

    def test_preserves_camera_cloud_and_preexisting_settings(self):
        proposed = prepare_settings(self.config, self.alignment)
        self.assertEqual(set(proposed["space_zones"]), {"space_001", "space_002"})
        self.assertEqual(proposed["source"], 1)
        self.assertEqual(proposed["supabase_url"], self.config["supabase_url"])
        self.assertTrue(proposed["camera_verified_external"])
        self.assertEqual(self.config["space_zones"], {})
        self.assertEqual(proposed["map_alignment"]["source"], "administrator-map-four-point")

    def test_wrong_camera_or_facility_is_rejected(self):
        for field in ("facility_id", "camera_id"):
            with self.subTest(field=field):
                altered = {**self.alignment,field:"different"}
                with self.assertRaisesRegex(ValueError, "一致しません"):
                    checked_alignment(self.config, altered)

    def test_mismatched_zone_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "対応していません"):
            checked_alignment(self.config, {**self.alignment, "space_uids": ["space_001"]})

    def test_camera_aspect_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "縦横比"):
            checked_alignment(self.config, {**self.alignment, "image_width": 640, "image_height": 480})

    def test_out_of_frame_and_overlapping_zones_are_rejected(self):
        changed=json.loads(json.dumps(self.alignment))
        changed["space_zones"]["space_002"][0][0]=1.1
        with self.assertRaisesRegex(ValueError, "範囲外"):
            checked_alignment(self.config, changed)
        changed=json.loads(json.dumps(self.alignment))
        changed["space_zones"]["space_002"]=changed["space_zones"]["space_001"]
        with self.assertRaises(ValueError):
            checked_alignment(self.config, changed)

    def test_dry_run_never_modifies_file_and_apply_creates_backup(self):
        with TemporaryDirectory() as folder:
            config=Path(folder)/"config.json"
            source=Path(folder)/"alignment.json"
            config.write_text(json.dumps(self.config),encoding="utf-8")
            source.write_text(json.dumps(self.alignment),encoding="utf-8")
            self.assertEqual(main(["--config",str(config),"--alignment",str(source)]),0)
            self.assertEqual(json.loads(config.read_text(encoding="utf-8")),self.config)
            with self.assertRaises(SystemExit):
                main(["--config",str(config),"--alignment",str(source),"--apply"])
            self.assertEqual(json.loads(config.read_text(encoding="utf-8")),self.config)
            updated=prepare_settings(self.config,self.alignment)
            backup=apply_file(config,updated)
            self.assertTrue(backup.is_file())
            self.assertEqual(json.loads(backup.read_text(encoding="utf-8")),self.config)
            self.assertEqual(set(json.loads(config.read_text(encoding="utf-8"))["space_zones"]),{"space_001","space_002"})


if __name__ == "__main__":
    unittest.main()
