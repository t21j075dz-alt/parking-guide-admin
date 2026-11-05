"""実カメラの重ね合わせ検証と区画設定の安全な取り込みを検証する。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from import_map_alignment import prepare_settings, read_json, validate_verification, main
from verify_map_alignment import (
    assert_camera_frame, build_receipt, preview_frame, write_receipt
)


class LiveCameraMapVerificationTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "facility_id": "home-test-001", "camera_id": "home-camera-01",
            "source": 1, "camera_kind": "usb", "camera_verified_external": True,
            "space_uids": ["space_001", "space_002"],
            "space_zones": {}, "calibration_capture": {
                "width": 1280, "height": 720, "source": "1", "kind": "usb"
            },
            "supabase_url": "https://example.invalid",
        }
        # Newly moved camera uses 4:3; live verification can override old 16:9 calibration.
        self.alignment = {
            "schema_version": 1, "facility_id": "home-test-001",
            "camera_id": "home-camera-01",
            "image_width": 640, "image_height": 480,
            "map_canvas": {"width": 1000, "height": 1000},
            "map_points": [[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
            "image_points": [[.15,.18],[.85,.18],[.85,.85],[.15,.85]],
            "space_uids": ["space_001", "space_002"],
            "space_zones": {
                "space_001": [[.15,.2],[.34,.2],[.34,.61],[.15,.61]],
                "space_002": [[.37,.2],[.56,.2],[.56,.61],[.37,.61]],
            },
        }

    def make_files(self, directory):
        config_file = Path(directory) / "config.json"
        alignment_file = Path(directory) / "alignment.json"
        config_file.write_text(json.dumps(self.config), encoding="utf-8")
        alignment_file.write_text(json.dumps(self.alignment), encoding="utf-8")
        return config_file, alignment_file

    def test_frame_requires_camera_source_and_matching_aspect(self):
        assert_camera_frame(self.config, self.alignment, 1280, 960)
        with self.assertRaisesRegex(ValueError, "縦横比"):
            assert_camera_frame(self.config, self.alignment, 1280, 720)
        invalid = {**self.config, "camera_verified_external": False}
        with self.assertRaisesRegex(ValueError, "目視確認"):
            assert_camera_frame(invalid, self.alignment, 1280, 960)

    def test_live_receipt_allows_recalibration_but_not_unknown_camera(self):
        with TemporaryDirectory() as folder:
            config_file, alignment_file = self.make_files(folder)
            receipt = build_receipt(self.config, self.alignment, alignment_file, 1280, 960)
            self.assertEqual(receipt["camera_source"], 1)
            verification_file = Path(folder) / "verified.json"
            write_receipt(verification_file, receipt)
            with self.assertRaises(FileExistsError):
                write_receipt(verification_file, receipt)
            accepted = validate_verification(
                self.config, self.alignment, read_json(verification_file), alignment_file
            )
            updated = prepare_settings(self.config, self.alignment, accepted)
            self.assertEqual(updated["calibration_capture"],
                             {"width":1280,"height":960,"source":"1","kind":"usb"})
            self.assertEqual(self.config["calibration_capture"]["height"], 720)
            self.assertEqual(updated["space_uids"], self.config["space_uids"])
            self.assertEqual(updated["supabase_url"], self.config["supabase_url"])
            self.assertEqual(updated["map_alignment"]["alignment_sha256"],
                             receipt["alignment_sha256"])
            # 旧方式の静止画に新しい縦横比を持ち込むことは拒否。
            with self.assertRaisesRegex(ValueError, "縦横比"):
                prepare_settings(self.config, self.alignment)

    def test_receipt_expires_and_rejects_tampering(self):
        with TemporaryDirectory() as folder:
            _, alignment_file = self.make_files(folder)
            receipt = build_receipt(self.config, self.alignment, alignment_file, 1280, 960)
            invalid = {**receipt, "camera_source": 2}
            with self.assertRaisesRegex(ValueError, "入力元"):
                validate_verification(self.config, self.alignment, invalid, alignment_file)
            old = {**receipt, "checked_at": (
                datetime.now(timezone.utc)-timedelta(days=8)).isoformat()}
            with self.assertRaisesRegex(ValueError, "期限外"):
                validate_verification(self.config, self.alignment, old, alignment_file)
            alignment_file.write_text(json.dumps({**self.alignment,"camera_id":"changed"}),
                                      encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "変更されています"):
                validate_verification(self.config, self.alignment, receipt, alignment_file)

    def test_live_receipt_imports_without_touching_other_settings(self):
        with TemporaryDirectory() as folder:
            config_file, alignment_file = self.make_files(folder)
            verification = build_receipt(self.config, self.alignment, alignment_file, 1280, 960)
            verification_file = Path(folder) / "verification.json"
            write_receipt(verification_file, verification)
            # --verification alone never writes; --apply is also required.
            self.assertEqual(main(["--config",str(config_file),
                                   "--alignment",str(alignment_file),
                                   "--verification",str(verification_file)]),0)
            self.assertEqual(read_json(config_file), self.config)
            self.assertEqual(main(["--config",str(config_file),
                                   "--alignment",str(alignment_file),
                                   "--verification",str(verification_file),
                                   "--apply"]),0)
            updated=read_json(config_file)
            self.assertEqual(updated["calibration_capture"]["height"],960)
            self.assertEqual(updated["source"],1)
            self.assertTrue(list(Path(folder).glob("config_backup_map_alignment_*.json")))

    def test_preview_polygons_render_without_modifying_frame(self):
        import cv2
        import numpy as np
        source=np.zeros((480,640,3),dtype=np.uint8)
        original=source.copy()
        rendered=preview_frame(source,self.alignment["space_zones"],cv2)
        self.assertEqual(rendered.shape,source.shape)
        self.assertTrue(np.array_equal(source,original))
        self.assertGreater(np.max(rendered),0)


if __name__ == "__main__":
    unittest.main()
