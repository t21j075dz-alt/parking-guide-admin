"""Tests for safe frame selection before any manual annotation."""
import unittest
from prepare_vehicle_mask_frames import sampling_seconds


class RawVideoSamplingTests(unittest.TestCase):
    def test_adds_regular_and_dense_turn_frames(self):
        seconds = sampling_seconds(205., interval=30.,
                                   focus_start=148., focus_end=190.,
                                   focus_step=2.)
        self.assertIn(0., seconds)
        self.assertIn(90., seconds)
        self.assertIn(148., seconds)
        self.assertIn(154., seconds)
        self.assertIn(170., seconds)
        self.assertIn(182., seconds)
        self.assertEqual(seconds, sorted(set(seconds)))
        self.assertNotIn(210., seconds)

    def test_short_video_has_no_turn_samples_out_of_range(self):
        seconds = sampling_seconds(30., interval=10.)
        self.assertEqual(seconds, [0., 10., 20.])

    def test_invalid_interval_rejected(self):
        for kwargs in ({"duration":0.}, {"duration":30.,"interval":0.},
                       {"duration":30.,"focus_step":-1.}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                sampling_seconds(**kwargs)


if __name__ == "__main__":
    unittest.main()
