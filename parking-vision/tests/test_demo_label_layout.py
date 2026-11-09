"""Recorded-video labels must not cover vehicle bodies or overlap one another."""
import sys
import unittest
from unittest.mock import patch

from video_demo_support import demo_badge_grid, draw_demo_phase_labels


class Frame:
    def __init__(self, width=1280, height=818):
        self.shape = (height, width, 3)


class FakeCV2:
    BORDER_CONSTANT = 0
    FONT_HERSHEY_SIMPLEX = 1
    LINE_AA = 16

    def __init__(self):
        self.boxes = []
        self.texts = []

    def copyMakeBorder(self, frame, top, bottom, left, right, method, value):
        return Frame(frame.shape[1], frame.shape[0] + bottom)

    def rectangle(self, frame, first, second, color, thickness):
        self.boxes.append((first, second, thickness))

    def putText(self, frame, message, pos, font, size, color, thickness, antialias):
        self.texts.append(message)


class DemoBadgesTests(unittest.TestCase):
    def test_six_labels_get_distinct_footer_columns_at_1280(self):
        self.assertEqual(demo_badge_grid(1280, 6), (6, 1, 213))
        self.assertEqual(demo_badge_grid(640, 6), (3, 2, 213))
        self.assertEqual(demo_badge_grid(900, 12), (4, 3, 225))
        with self.assertRaises(ValueError):
            demo_badge_grid(100, 6)

    def test_no_boxes_cover_any_part_of_original_frame(self):
        six = {f"space_{i:03d}": [] for i in range(1, 7)}
        original = Frame()
        cv2 = FakeCV2()
        phases = dict.fromkeys(six, "stopped")
        # Force English fallback to make this test independent of local fonts
        # or Pillow/OpenCV installation. Verify the panel coordinates only.
        with patch.dict(sys.modules, {"PIL": None}):
            result = draw_demo_phase_labels(original, cv2, six, phases)
        self.assertGreater(result.shape[0], original.shape[0])
        self.assertEqual(len(cv2.boxes), 12)
        filled = [(a, b) for a, b, thickness in cv2.boxes if thickness == -1]
        self.assertEqual(len(filled), 6)
        self.assertTrue(all(a[1] >= original.shape[0] for a, b in filled))
        self.assertTrue(all(a[1] < b[1] and a[0] < b[0] for a, b in filled))
        self.assertEqual(len(set((a[0], a[1]) for a, _ in filled)), 6)

    def test_compact_version_scales_to_many_stalls(self):
        many = {f"space_{i:03d}": [] for i in range(1, 18)}
        cv2 = FakeCV2()
        result = draw_demo_phase_labels(Frame(1280, 818), cv2, many, {})
        self.assertEqual(result.shape[0], 852)
        self.assertEqual(cv2.boxes, [])
        self.assertTrue(any("RECORDED SPACES 17" in t for t in cv2.texts))


if __name__ == "__main__":
    unittest.main()
