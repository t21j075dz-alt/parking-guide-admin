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

    def test_unique_turn_accepts_moderate_color_match_below_standard_gate(self):
        matching=StableIdMatcher(max_missing=12)
        old=detection(1,.477,.757,appearance=[1,0])
        old["bbox"]=[481,385,741,545]
        new=detection(42,.741,.995,appearance=[.445,.896])
        new["bbox"]=[669,504,1227,720]
        self.assertEqual(matching.update([old],592)[0]["track_id"],1)
        self.assertEqual(matching.update([new],594)[0]["track_id"],1)

    def test_turn_reid_does_not_bridge_different_color(self):
        matching = StableIdMatcher(max_missing=12)
        a = detection(1, .72, .83, appearance=[1,0,0])
        a["bbox"] = [890,400,1280,690]
        b = detection(3, .43, .73, appearance=[0,1,0])
        b["bbox"] = [420,420,720,650]
        self.assertEqual(matching.update([a], 0)[0]["track_id"], 1)
        self.assertEqual(matching.update([b], 5.8)[0]["track_id"], 2)

    def test_foreground_turn_id_three_to_four_is_same_car(self):
        # The supplied recording shows a lower, larger vehicle rectangle
        # after a sharp turn. Matching only bbox IoU loses the ID.
        matcher = StableIdMatcher(max_missing=12)
        before = detection(3, .48, .76, appearance=[.91,.09,0])
        before["bbox"] = [481,385,741,545]
        after = detection(4, .74, .99, appearance=[.90,.10,0])
        after["bbox"] = [704,507,1162,718]
        self.assertEqual(matcher.update([before], 594)[0]["track_id"],1)
        self.assertEqual(matcher.update([after], 596)[0]["track_id"],1)

    def test_turning_white_car_with_realistic_appearance_drop(self):
        # On two sample frames from the user's annotated video, approximate
        # HSV colour similarity dropped to 0.75 after the car rotated.
        matcher = StableIdMatcher(max_missing=12)
        before = detection(3,.48,.76,appearance=[1.0,0.0])
        before["bbox"]=[481,385,741,545]
        after = detection(4,.74,.99,appearance=[.75,.66])
        after["bbox"]=[704,507,1162,718]
        self.assertEqual(matcher.update([before],594)[0]["track_id"],1)
        self.assertEqual(matcher.update([after],596)[0]["track_id"],1)

    def test_raw_same_id_after_large_turn_and_seven_second_occlusion(self):
        # Actual footage: first car left the sixth stall and reappeared
        # roughly seven video seconds later approaching the third stall.
        matcher = StableIdMatcher(max_missing=12)
        a = detection(1,.68,.99,appearance=[1.0,0.0])
        a["bbox"]=[608,499,1133,714]
        b = detection(1,.43,.82,appearance=[.82,.57])
        b["bbox"]=[428,408,674,594]
        self.assertEqual(matcher.update([a],162)[0]["track_id"],1)
        self.assertEqual(matcher.update([b],169)[0]["track_id"],1)

    def test_new_raw_id_with_color_shift_at_foreground_turn(self):
        # Crops from the user's 593s and 595s YOLO overlay were around
        # 0.71 cosine similarity, so this tests an adverse 0.63 case.
        matcher = StableIdMatcher(max_missing=12)
        a = detection(1,.477,.76,appearance=[1,0])
        a["bbox"]=[481,385,741,545]
        b = detection(42,.72,.99,appearance=[.63,.78])
        b["bbox"]=[701,507,1153,717]
        self.assertEqual(matcher.update([a],593)[0]["track_id"],1)
        self.assertEqual(matcher.update([b],595)[0]["track_id"],1)

    def test_same_raw_id_1_after_six_second_turn_with_low_color(self):
        matcher=StableIdMatcher(max_missing=12)
        before=detection(1, .734, .998, appearance=[1,0,0])
        before["bbox"]=[650,509,1230,720]
        after=detection(1, .425, .846, appearance=[0,1,0])
        after["bbox"]=[425,415,663,610]
        self.assertEqual(matcher.update([before],162)[0]["track_id"],1)
        det=matcher.update([after],168)[0]
        self.assertEqual(det["track_id"],1)
        self.assertFalse(det["id_reassociated"])
        self.assertEqual(matcher.new_tracks,1)

    def test_single_car_42_raw_turn_in_two_seconds(self):
        matcher=StableIdMatcher(max_missing=12)
        previous=detection(1,.477,.757,appearance=[1,.35,.1])
        previous["bbox"]=[481,385,741,545]
        current=detection(42,.741,.995,appearance=[.78,.50,.1])
        current["bbox"]=[669,504,1227,720]
        self.assertEqual(matcher.update([previous],592)[0]["track_id"],1)
        after=matcher.update([current],594)[0]
        self.assertEqual(after["track_id"],1)
        self.assertTrue(after["id_reassociated"])

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
