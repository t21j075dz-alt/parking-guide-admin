"""YOLOが別の番号を付けても、区画動画内でIDを保持するためのテスト。"""
import unittest

from stable_ids import StableIdMatcher


def detection(raw, x, y, name="car", appearance=None):
    return {"track_id": raw, "point": (x, y), "name": name,
            "appearance": appearance, "bbox": [0, 0, 100, 100]}


class StableIdTest(unittest.TestCase):
    def test_same_car_new_yolo_id_keeps_stable_number(self):
        matching = StableIdMatcher(max_missing=10)
        self.assertEqual(matching.update([detection(1, 0.40, 0.80)], 0)[0]["track_id"], 1)
        self.assertEqual(matching.update([detection(1, 0.43, 0.80)], 1)[0]["track_id"], 1)
        actual = matching.update([detection(13, 0.46, 0.80)], 2)[0]
        self.assertEqual(actual["track_id"], 1)
        self.assertEqual(actual["raw_track_id"], 13)
        self.assertEqual(matching.reassociated, 1)

    def test_two_cars_visible_together_remain_distinct(self):
        matching = StableIdMatcher()
        initial = matching.update([detection(1, 0.3, 0.8), detection(2, 0.6, 0.8)], 0)
        self.assertEqual([i["track_id"] for i in initial], [1, 2])
        after = matching.update([detection(1, 0.31, 0.8), detection(3, 0.60, 0.8)], 1)
        self.assertEqual([i["track_id"] for i in after], [1, 2])

    def test_far_object_is_not_merged(self):
        matching = StableIdMatcher()
        matching.update([detection(1, 0.1, 0.1)], 0)
        after = matching.update([detection(11, 0.9, 0.9)], 1)
        self.assertEqual(after[0]["track_id"], 2)

    def test_different_color_is_not_merged(self):
        matching = StableIdMatcher()
        matching.update([detection(1, 0.40, 0.40, appearance=[1, 0, 0])], 0)
        after = matching.update([detection(11, 0.42, 0.4, appearance=[0, 1, 0])], 1)
        self.assertEqual(after[0]["track_id"], 2)

    def test_gap_over_limit_is_new_session(self):
        matching = StableIdMatcher(max_missing=5)
        matching.update([detection(1, 0.4, 0.4)], 0)
        after = matching.update([detection(11, 0.4, 0.4)], 7)
        self.assertEqual(after[0]["track_id"], 2)

    def test_ambiguous_candidates_receive_new_id(self):
        matching = StableIdMatcher()
        matching.update([detection(1, 0.4, 0.4), detection(2, 0.42, 0.4)], 0)
        updated = matching.update([detection(3, 0.41, 0.4)], 1)
        self.assertEqual(updated[0]["track_id"], 3)


if __name__ == "__main__":
    unittest.main()
