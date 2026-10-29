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

    def test_one_car_turns_with_large_bbox_shift_and_new_raw_id(self):
        matching = StableIdMatcher(max_missing=12)
        original = detection(1, .72, .83, appearance=[.9, .1, .0])
        original["bbox"] = [890, 400, 1280, 690]
        next_car = detection(3, .43, .73, appearance=[.91, .09, 0.])
        next_car["bbox"] = [420, 420, 720, 650]
        self.assertEqual(matching.update([original], 0)[0]["track_id"], 1)
        changed = matching.update([next_car], 5.8)[0]
        self.assertEqual(changed["track_id"], 1)
        self.assertEqual(changed["raw_track_id"], 3)

    def test_turn_reid_does_not_bridge_different_color(self):
        matching = StableIdMatcher(max_missing=12)
        a = detection(1, .72, .83, appearance=[1,0,0])
        a["bbox"] = [890,400,1280,690]
        b = detection(3, .43, .73, appearance=[0,1,0])
        b["bbox"] = [420,420,720,650]
        self.assertEqual(matching.update([a], 0)[0]["track_id"], 1)
        self.assertEqual(matching.update([b], 5.8)[0]["track_id"], 2)

    def test_short_yolo_id_dropout_keeps_stable_car_identity(self):
        matcher = StableIdMatcher(max_missing=8)
        first = detection(3, .43, .73, appearance=[.9,.1,0])
        first["bbox"] = [420,420,720,650]
        unknown = detection(None, .44, .73, appearance=[.9,.1,0])
        unknown["bbox"] = [425,420,730,650]
        renewed = detection(4, .45, .73, appearance=[.9,.1,0])
        renewed["bbox"] = [430,420,735,650]
        self.assertEqual(matcher.update([first], 0)[0]["track_id"], 1)
        mid=matcher.update([unknown], 1)[0]
        self.assertEqual(mid["track_id"],1)
        self.assertIsNone(mid["raw_track_id"])
        self.assertEqual(matcher.update([renewed],2)[0]["track_id"],1)

    def test_large_turn_reid_requires_a_single_car_scene(self):
        matching = StableIdMatcher(max_missing=12)
        a = detection(1, .72, .83, appearance=[1,0,0])
        a["bbox"] = [890,400,1280,690]
        c = detection(2, .12, .2, appearance=[0,1,0])
        c["bbox"] = [100,100,230,200]
        matching.update([a,c],0)
        b = detection(3, .43, .73, appearance=[1,0,0])
        b["bbox"] = [420,420,720,650]
        new = matching.update([b],5.8)[0]
        self.assertNotEqual(new["track_id"], 1)

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
