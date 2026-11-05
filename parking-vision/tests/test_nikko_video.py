"""日光の画角内全区画の登録・録画専用出力を安全に扱う回帰テスト。"""
from datetime import datetime, timezone
import csv
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from nikko_video_config import (
    FACILITY_ID, CAMERA_ID, visible_space_uids, make_config, checked_config,
    record_video_calibration, checked_ready, ensure_file, read_settings,
)
from import_nikko_map_alignment import (
    checked_projection, proposed_config, save_config,
)
from export_nikko_recording import convert_recording_log
from recorded_parking_states import RecordedParkingStateMachine
from video_demo_support import require_demo_mode, demo_status_rows, SOURCE


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


if __name__ == "__main__":
    unittest.main()
