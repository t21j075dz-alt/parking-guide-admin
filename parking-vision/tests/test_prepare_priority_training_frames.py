"""Offline tests for priority sampling of raw parking recordings."""
import unittest

from prepare_priority_training_frames import (
    parse_focus_ranges, select_timestamps,
)


class PriorityTrainingFramesTests(unittest.TestCase):
    def test_parse_multiple_named_windows_and_clip_to_duration(self):
        windows = parse_focus_ranges(
            ["154-169:turning", "170-185:bay_entry", "590-610:exit"], 600.)
        self.assertEqual(windows, [(154., 169., "turning"),
                                   (170., 185., "bay_entry"),
                                   (590., 600., "exit")])

    def test_reject_ambiguous_or_out_of_range_windows(self):
        for value in ["154-169", "170-154:turn", "-2-10:turn",
                      "650-700:turn", "abc-10:turn", "5-10:車"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_focus_ranges([value], 600.)

    def test_regular_and_dense_samples_are_ordered_and_tagged(self):
        rows = select_timestamps(
            40., interval=10., focus_step=2.,
            windows=[(14., 19., "turn"), (16., 20., "occlusion")])
        times = [timestamp for timestamp, _ in rows]
        self.assertEqual(times, sorted(set(times)))
        self.assertIn((0., []), rows)
        self.assertIn((14., ["turn"]), rows)
        self.assertIn((16., ["occlusion", "turn"]), rows)
        self.assertIn((18., ["occlusion", "turn"]), rows)
        self.assertIn((20., []), rows)
        self.assertFalse(any(t >= 40. for t in times))

    def test_regular_sampling_without_focus(self):
        self.assertEqual(
            select_timestamps(25., interval=10., focus_step=2., windows=[]),
            [(0., []), (10., []), (20., [])])

    def test_bad_intervals_are_rejected(self):
        for value in [0., -1., float("nan"), float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_timestamps(100., interval=value, focus_step=2.,
                                  windows=[])


if __name__ == "__main__":
    unittest.main()
