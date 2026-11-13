"""日光の画角内全区画の登録・録画専用出力を安全に扱う回帰テスト。"""
from datetime import datetime, timezone
import csv
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nikko_video_config import (
    FACILITY_ID, CAMERA_ID, visible_space_uids, make_config, checked_config,
    record_video_calibration, checked_ready, ensure_file, read_settings,
)
from import_nikko_map_alignment import (
    checked_projection, proposed_config, save_config,
)
from export_nikko_recording import convert_recording_log
from recorded_parking_states import RecordedParkingStateMachine
from video_demo_support import require_demo_mode, demo_status_rows, SOURCE, invalidate_nikko_outside_camera_rows


def base_settings():
    return {
        "facility_id": "home-test-001", "camera_id": "home-camera-01",
        "source": 1,
        "vehicle_model": "test-model.pt",
        "supabase_url": "https://example.invalid",
        "publishable_key": "synthetic-public-key-for-tests",
        "space_uids": ["space_001"],
        "space_zones": {},
    }


def visible_zones(ids):
    # Four equally sized rows; enough spacing to avoid overlap warnings.
    result = {}
    for index, uid in enumerate(ids):
        col, row = index % 6, index // 6
        x, y = .05 + col * .15, .06 + row * .18
        result[uid] = [[x, y], [x+.09, y], [x+.09, y+.11], [x, y+.11]]
    return result


class NikkoDynamicSpaceTests(unittest.TestCase):
    def test_any_visible_count_not_hardcoded_to_eight(self):
        ids = visible_space_uids(24)
        self.assertEqual(len(ids), 24)
        self.assertEqual(ids[0], "space_001")
        self.assertEqual(ids[-1], "space_024")
        manual = visible_space_uids(space_uids="space_002,space_009,space_044")
        self.assertEqual(manual, ["space_002", "space_009", "space_044"])
        with self.assertRaisesRegex(ValueError, "併用"):
            visible_space_uids(12, "space_001")
        with self.assertRaises(ValueError):
            visible_space_uids(0)
        with self.assertRaises(ValueError):
            visible_space_uids(1000)
        with self.assertRaises(ValueError):
            visible_space_uids(space_uids="space_001,space_001")

    def test_video_fingerprint_prevents_reusing_zones_for_another_video(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder)/"first.mp4", Path(folder)/"second.mp4"
            first.write_bytes(b"original-video-data")
            second.write_bytes(b"a-different-video-data")
            ids = visible_space_uids(12)
            config = make_config(base_settings(), ids)
            config["space_zones"] = visible_zones(ids)
            record_video_calibration(config, first, 1280, 720)
            self.assertEqual(len(checked_ready(config, first)), 12)
            with self.assertRaisesRegex(ValueError, "異なります"):
                checked_ready(config, second)
            self.assertEqual(config["source"], -1)
            self.assertFalse(config["camera_snapshots_enabled"])

    def test_only_separate_config_is_written_and_reset_is_backed_up(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)/"config.json"
            dest = Path(folder)/"config_nikko_video_demo.json"
            base.write_text(json.dumps(base_settings()),encoding="utf-8")
            config, created = ensure_file(base,dest,ids=visible_space_uids(18))
            self.assertTrue(created)
            self.assertEqual(len(config["space_uids"]),18)
            self.assertEqual(read_settings(base)["facility_id"],"home-test-001")
            self.assertEqual(ensure_file(base,dest)[1],False)
            with self.assertRaisesRegex(ValueError, "reset-zones"):
                ensure_file(base,dest,ids=visible_space_uids(21))
            replacement,_ = ensure_file(base,dest,ids=visible_space_uids(21),reset=True)
            self.assertEqual(len(replacement["space_uids"]),21)
            self.assertTrue(list(Path(folder).glob("config_nikko_video_demo_backup_*.json")))
            self.assertEqual(read_settings(base)["facility_id"],"home-test-001")
            with self.assertRaises(ValueError):
                ensure_file(base,base,ids=visible_space_uids(21))

    def test_map_projection_records_only_visible_irregular_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/"nikko.mp4"
            video.write_bytes(b"source-video-for-tests")
            ids=["space_002","space_009","space_044"]
            alignment={
                "schema_version":1,
                "facility_id":FACILITY_ID,"camera_id":CAMERA_ID,
                "space_uids":ids,
                "excluded_space_uids":["space_001","space_010","space_050"],
                "space_zones":visible_zones(ids),
                "image_width":1280,"image_height":720,
                "map_points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
                "image_points":[[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
            }
            zones,excluded,dimensions,warnings=checked_projection(alignment)
            self.assertEqual(len(zones),3)
            self.assertEqual(len(excluded),3)
            config=make_config(base_settings(),ids)
            updated=proposed_config(config,alignment,zones,video,dimensions)
            self.assertEqual(set(updated["space_zones"]),set(ids))
            self.assertNotIn("space_001",updated["space_zones"])
            self.assertEqual(updated["excluded_space_uids"],excluded)
            self.assertEqual(len(checked_ready(updated,video)),3)
            out=Path(folder)/"nikko-config.json"
            save_config(out,updated)
            self.assertEqual(read_settings(out)["space_uids"],ids)
            modified={**updated,"source":20}
            with self.assertRaisesRegex(ValueError,"入力"):
                checked_config(modified)
            with self.assertRaisesRegex(ValueError,"重複"):
                checked_projection({**alignment,"excluded_space_uids":["space_002"]})

    def test_multipoint_alignment_accepts_six_to_twentyfour_pairs(self):
        points = [[.1,.1],[.9,.1],[.9,.9],[.1,.9],[.4,.3],[.7,.7]]
        data = {
            "schema_version": 1,
            "facility_id": FACILITY_ID, "camera_id": CAMERA_ID,
            "space_uids": ["space_001"],
            "space_zones": visible_zones(["space_001"]),
            "excluded_space_uids": ["space_059"],
            "image_width": 1920, "image_height": 1080,
            "map_points": points, "image_points": points,
            "alignment_quality": {
                "method": "ransac-least-squares",
                "point_count": 6, "inlier_count": 6,
                "outlier_indices": [], "rms_pixels": .46,
            },
        }
        zones, excluded, size, _ = checked_projection(data)
        self.assertEqual(len(zones), 1)
        self.assertEqual(excluded, ["space_059"])
        self.assertEqual(size, (1920, 1080))
        with self.assertRaisesRegex(ValueError, "4～24"):
            checked_projection({**data, "image_points": points[:5]})
        with self.assertRaisesRegex(ValueError, "精度診断"):
            checked_projection({**data, "alignment_quality": {
                **data["alignment_quality"], "outlier_indices": [2]}})
        with self.assertRaisesRegex(ValueError, "精度診断"):
            checked_projection({**data, "alignment_quality": {
                **data["alignment_quality"], "rms_pixels": float("nan")}})
        with self.assertRaisesRegex(ValueError, "4～24"):
            checked_projection({**data, "map_points": points*5,
                                "image_points": points*5})
        legacy = {**data, "map_points": points[:4], "image_points": points[:4]}
        legacy.pop("alignment_quality")
        self.assertEqual(len(checked_projection(legacy)[0]), 1)

    def test_photo_only_and_hybrid_camera_zones_preserve_original_map_uids(self):
        visible = ["space_001", "space_023"]
        rows = {
            "schema_version": 1, "facility_id": FACILITY_ID, "camera_id": CAMERA_ID,
            "alignment_method": "manual-zones",
            "space_uids": visible,
            "space_zones": visible_zones(visible),
            "excluded_space_uids": ["space_059"],
            "manual_zone_uids": visible,
            "image_width": 1920, "image_height": 1080,
            "map_points": [], "image_points": [],
        }
        zones, outside, dimensions, warnings = checked_projection(rows)
        self.assertEqual(set(zones), set(visible))
        self.assertEqual(outside, ["space_059"])
        self.assertEqual(dimensions, (1920, 1080))
        with self.assertRaisesRegex(ValueError, "4～24"):
            checked_projection({**rows, "map_points": [[.1,.1]], "image_points": [[.1,.1]]})
        with self.assertRaisesRegex(ValueError, "手動登録"):
            checked_projection({**rows, "manual_zone_uids": ["space_001"]})
        with self.assertRaisesRegex(ValueError, "精度診断"):
            checked_projection({**rows, "alignment_quality": {"rms_pixels": 0}})
        hybrid = {**rows, "alignment_method": "hybrid-zones",
                  "map_points": [[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
                  "image_points": [[.1,.1],[.9,.1],[.9,.9],[.1,.9]],
                  "manual_zone_uids": ["space_023"]}
        self.assertEqual(set(checked_projection(hybrid)[0]), set(visible))
        # 15点中の一部が外れ点でも、個別補正したハイブリッドは履歴を保持できる。
        points = [[.10 + (i % 5) * .15, .10 + (i // 5) * .30] for i in range(15)]
        hybrid_rough = {**hybrid, "map_points": points, "image_points": points,
                        "alignment_quality": {
                            "method": "ransac-least-squares", "point_count": 15,
                            "inlier_count": 7,
                            "outlier_indices": [7,8,9,10,11,12,13,14],
                            "rms_pixels": 10.6,
                        }}
        self.assertEqual(set(checked_projection(hybrid_rough)[0]), set(visible))
        with self.assertRaisesRegex(ValueError, "精度診断"):
            checked_projection({**hybrid_rough, "alignment_method": "global-homography",
                                "manual_zone_uids": []})
        with self.assertRaisesRegex(ValueError, "精度診断"):
            checked_projection({**hybrid_rough, "alignment_quality": {
                **hybrid_rough["alignment_quality"], "outlier_indices": [[7]]}})
        with self.assertRaisesRegex(ValueError, "位置合わせ方法"):
            checked_projection({**rows, "alignment_method": "untrusted-method"})

    def test_unverified_nikko_stalls_remain_unknown(self):
        ids=visible_space_uids(18)
        machine=RecordedParkingStateMachine(ids,initially_confirmed_empty_uids=["space_002"])
        statuses,phases=machine.update([],visible_zones(ids),lambda *args: False,0.0)
        self.assertEqual(statuses["space_002"],"available")
        self.assertEqual(statuses["space_001"],"unknown")
        statuses,_=machine.update([],visible_zones(ids),lambda *args: False,6.0)
        self.assertEqual(statuses["space_018"],"unknown")

    def test_recorded_rows_only_use_nikko_demo_id(self):
        ids=visible_space_uids(14)
        config=make_config(base_settings(),ids)
        rows=demo_status_rows(config,{ids[0]:"unknown"},
                              datetime.now(timezone.utc).isoformat(),
                              {ids[0]:"unknown"})
        self.assertEqual(rows[0]["facility_id"],FACILITY_ID)
        self.assertEqual(rows[0]["source"],SOURCE)
        self.assertEqual(rows[0]["status"],"unknown")
        with self.assertRaises(ValueError):
            demo_status_rows(base_settings(),{ids[0]:"unknown"},"now")

    def test_export_handles_all_visible_ids_instead_of_eight(self):
        with tempfile.TemporaryDirectory() as folder:
            ids=visible_space_uids(21)
            log=Path(folder)/"区画状態の変化.csv"
            with log.open("w",encoding="utf-8-sig",newline="") as output:
                writer=csv.writer(output)
                writer.writerow(["判定日時","録画経過秒数","区画UID","判定状態","車両段階","周回"])
                for uid in ids:
                    writer.writerow(["now","0.0",uid,"unknown","unknown",1])
                writer.writerow(["now","2.0",ids[0],"occupied","stopped",1])
                writer.writerow(["now","0.0",ids[0],"available","available",2])
            result=convert_recording_log(log,Path(folder)/"user.csv",
                                         duration=6.0,space_uids=ids)
            with result.open("r",encoding="utf-8-sig",newline="") as stream:
                data=list(csv.DictReader(stream))
            self.assertEqual(len([item for item in data if item["動画の時刻(秒)"]=="6.000"]),21)
            self.assertEqual(data[-1]["動画の時刻(秒)"],"6.000")
            self.assertNotIn("space_999",{item["駐車枠ID"] for item in data})


    def test_switching_recordings_expires_earlier_out_of_frame_spaces(self):
        class FakeWriter:
            url="https://example.supabase.co"
            key="example-publishable"
            access_token="example-user-jwt"
            rows=None
            def _ensure_token(self):pass
            def upsert(self, table, rows, conflict):
                self.rows=rows
                self.table=table
                self.conflict=conflict
        class Reply:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):
                return b'[{"space_uid":"space_002"},{"space_uid":"space_009"},{"space_uid":"space_044"}]'
        def fake_get(req,timeout=10):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("nikko-test-001",req.full_url)
            self.assertNotIn("home-video-demo-001",req.full_url)
            return Reply()
        writer=FakeWriter()
        with patch("video_demo_support.request.urlopen",fake_get):
            changed=invalidate_nikko_outside_camera_rows(writer,["space_002","space_044"])
        self.assertEqual(changed,1)
        self.assertEqual(writer.table,"parking_live_status")
        self.assertEqual(writer.rows[0]["space_uid"],"space_009")
        self.assertEqual(writer.rows[0]["status"],"unknown")
        self.assertTrue(writer.rows[0]["checked_at"].startswith("2000-01-01"))


if __name__ == "__main__":
    unittest.main()
