"""Desktop migration preserves laptop stall polygons but never stale camera/empty state."""
import unittest
from copy import deepcopy

from camera_profiles import assert_calibrated_view
from transfer_home_zones import source_zones, transfer_settings


def laptop_settings():
    ids = [f"space_{n:03d}" for n in range(1, 7)]
    zones = {}
    for i, uid in enumerate(ids):
        left = 0.04 + .15 * i
        right = left + .13
        # Deliberately crossed click order from an older calibration.
        zones[uid] = [[left, .20], [right, .80], [right, .20], [left, .80]]
    return {
        "facility_id": "home-test-001",
        "space_uids": ids,
        "space_zones": zones,
        "camera_kind": "usb",
        "source": 1,
        "camera_backend": "msmf",
        "vehicle_model": r"C:\laptop\weights\best.pt",
        "calibration_capture": {
            "source": "1", "kind": "usb", "width": 1280, "height": 720,
        },
        "entry_zone": [], "exit_zone": [],
        "initially_confirmed_empty_uids": ["space_003"],
    }


def desktop_settings():
    return {
        "facility_id": "home-test-001",
        "space_uids": ["space_001"],
        "space_zones": {},
        "source": 0,
        "camera_verified_external": True,
        "camera_kind": "usb",
        "camera_backend": "dshow",
        "vehicle_model": r"C:\desktop\weights\best.pt",
        "publishable_key": "desktop-key",
        "initially_confirmed_empty_uids": ["space_001"],
        "initial_empty_verified_at": "2026-10-28T10:00:00+00:00",
        "allow_unverified_initial_empty": True,
    }


class HomeZoneTransferTest(unittest.TestCase):
    def test_all_six_zones_transfer_without_overwriting_desktop_hardware(self):
        old, desktop = laptop_settings(), desktop_settings()
        result = transfer_settings(old, desktop, 1920, 1080)
        self.assertEqual(len(result["space_zones"]), 6)
        self.assertEqual(result["space_uids"], old["space_uids"])
        self.assertEqual(result["source"], 0)
        self.assertEqual(result["camera_backend"], "dshow")
        self.assertEqual(result["vehicle_model"], desktop["vehicle_model"])
        self.assertEqual(result["publishable_key"], "desktop-key")
        self.assertEqual(result["calibration_capture"], {
            "width": 1920, "height": 1080, "source": "0", "kind": "usb",
        })
        self.assertEqual(result["initially_confirmed_empty_uids"], [])
        self.assertNotIn("initial_empty_verified_at", result)
        self.assertFalse(result["allow_unverified_initial_empty"])
        assert_calibrated_view(result, 1920, 1080)
        self.assertEqual(len(desktop["space_zones"]), 0)
        self.assertEqual(old["source"], 1)

    def test_reject_wrong_aspect_ratio(self):
        with self.assertRaisesRegex(ValueError, "縦横比"):
            transfer_settings(laptop_settings(), desktop_settings(), 1280, 960)

    def test_reject_unverified_camera(self):
        desktop = desktop_settings()
        desktop["camera_verified_external"] = False
        with self.assertRaisesRegex(ValueError, "目視確認"):
            transfer_settings(laptop_settings(), desktop, 1280, 720)

    def test_reject_missing_six_stall_locations(self):
        old = laptop_settings()
        old["space_zones"].pop("space_006")
        with self.assertRaisesRegex(ValueError, "未登録"):
            source_zones(old)

    def test_reject_different_facility(self):
        old = laptop_settings()
        old["facility_id"] = "another-test-site"
        with self.assertRaisesRegex(ValueError, "自宅駐車場"):
            transfer_settings(old, desktop_settings(), 1280, 720)

    def test_reject_different_camera_kind(self):
        old = laptop_settings()
        old["camera_kind"] = "camo"
        with self.assertRaisesRegex(ValueError, "Camo"):
            transfer_settings(old, desktop_settings(), 1280, 720)

    def test_accept_old_backup_without_capture_metadata_with_visual_check(self):
        old = laptop_settings()
        old.pop("calibration_capture")
        result = transfer_settings(old, desktop_settings(), 1280, 720)
        self.assertEqual(result["calibration_capture"]["source"], "0")


if __name__ == "__main__":
    unittest.main()
