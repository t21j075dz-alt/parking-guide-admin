"""日光のように駐車車両が多く、YOLO生IDが次々変わる環境を模擬する。"""
import unittest
from stable_ids import StableIdMatcher


def fake_car(raw_id, x, y):
    return {
        "track_id": raw_id, "name": "car",
        "point": (x, y),
        "bbox": [x*1000-16, y*1000-20, x*1000+16, y*1000+20],
        "confidence": .90,
    }


class DenseParkingRegression(unittest.TestCase):
    def test_twelve_stationary_vehicles_keep_twelve_stable_ids(self):
        matcher = StableIdMatcher(max_missing=12)
        observed = {}
        first = None
        for t in range(30):
            detections = []
            for i in range(12):
                x = .1 + (i % 4)*.2
                y = .15 + (i // 4)*.25
                # 7フレームごとに生IDが全台入れ替わる
                detections.append(fake_car(i + 1 + (t//7)*100, x, y))
            ids = [d["track_id"] for d in matcher.update(detections, float(t)*.033)]
            self.assertEqual(len(ids), len(set(ids)))  # 同じフレーム内では重複IDなし
            if first is None:
                first = ids
            self.assertEqual(ids, first)
        self.assertEqual(matcher.new_tracks, 12)
        self.assertEqual(matcher.reassociated, 48)

    def test_same_raw_id_reused_in_distant_location_must_not_merge(self):
        matcher = StableIdMatcher()
        matcher.update([fake_car(1, .2, .2)], 0)
        ids = matcher.update([fake_car(1, .8, .8)], 1)
        self.assertEqual(ids[0]["track_id"], 2)

    def test_detector_has_no_track_id_does_not_invent_one(self):
        matcher = StableIdMatcher()
        d = fake_car(1, .2, .2)
        d["track_id"] = None
        actual = matcher.update([d], 0)[0]
        self.assertIsNone(actual["track_id"])


if __name__ == "__main__":
    unittest.main()
