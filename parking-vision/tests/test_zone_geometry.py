"""Regression: camera calibration corners may be clicked in any order."""
import unittest

from monitor import inside, load_config, space_for
from zone_geometry import normalize_corners, audit_zones


class ZoneGeometryRegressionTest(unittest.TestCase):
    def test_crossed_click_order_is_repaired(self):
        crossing = [[.1, .2], [.3, .5], [.3, .2], [.1, .5]]
        ordered = normalize_corners(crossing)
        self.assertTrue(inside((.2, .35), ordered))
        self.assertFalse(inside((.7, .35), ordered))
        self.assertEqual(space_for((.2, .35), {"space_001": ordered}), "space_001")

    def test_reject_duplicate_and_collinear_points(self):
        with self.assertRaises(ValueError):
            normalize_corners([[.1,.1],[.1,.1],[.3,.3],[.3,.1]])
        with self.assertRaises(ValueError):
            normalize_corners([[.1,.1],[.2,.2],[.3,.3],[.4,.4]])

    def test_detect_real_stall_overlap_but_not_touching_edge(self):
        touching = {
            "A": normalize_corners([[.1,.3],[.4,.3],[.4,.8],[.1,.8]]),
            "B": normalize_corners([[.4,.3],[.7,.3],[.7,.8],[.4,.8]]),
        }
        self.assertFalse(any("重なって" in s for s in audit_zones(touching)))
        overlapping = {**touching,
                       "C": normalize_corners([[.2,.35],[.6,.35],[.6,.85],[.2,.85]])}
        self.assertTrue(any("重なって" in s for s in audit_zones(overlapping)))


if __name__ == "__main__":
    unittest.main()
