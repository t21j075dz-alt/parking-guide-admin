# -*- coding: utf-8 -*-
"""Draw-only position smoothing; raw bbox and occupancy remain unchanged."""
import unittest

import cv2
import numpy as np

from tracking_presentation import TrackingPresentation, visible_major_axis
from vehicle_segmentation import polygon_area_centroid


def observation(tid, x1, y1, x2, y2, mask=True):
    item = {
        "track_id": tid, "name": "car",
        "bbox": [x1,y1,x2,y2],
        "confidence": .91,
    }
    if mask:
        item.update({
            "segmentation_contour": [(x1,y1),(x2,y1),(x2,y2),(x1,y2)],
            "segmentation_bbox": [x1+2,y1+2,x2-2,y2-2],
            "segmentation_match_iou": .91,
            "segmentation_confidence": .92,
        })
    return item


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.present = TrackingPresentation()

    def test_display_box_smooths_jitter_only(self):
        first = observation(1,100,120,300,220)
        self.present.update([first], 0., (720,1280,3))
        second = observation(1,110,120,310,220)
        self.present.update([second], .1, (720,1280,3))
        self.assertEqual(second["bbox"], [110,120,310,220])
        self.assertLess(second["display_bbox"][0],110.)
        self.assertGreater(second["display_bbox"][0],100.)
        self.assertEqual(second["display_bbox_source"],"smoothed-mask")

    def test_separate_cars_have_separate_state(self):
        first = observation(1,100,120,300,220)
        second = observation(2,700,120,900,220)
        self.present.update([first,second],0,(720,1280,3))
        continued = observation(2,705,120,905,220)
        self.present.update([continued],.1,(720,1280,3))
        self.assertGreater(continued["display_bbox"][0],690)

    def test_large_teleport_snaps_without_ghost_box(self):
        first = observation(1,100,120,300,220)
        moved = observation(1,800,120,1000,220)
        self.present.update([first],0,(720,1280,3))
        self.present.update([moved],.1,(720,1280,3))
        self.assertEqual(moved["display_bbox"][0], 802.)

    def test_reset_for_new_replay_loop(self):
        self.present.update([observation(1,100,120,300,220)],0,(720,1280,3))
        self.present.reset()
        next_loop = observation(1,110,120,310,220)
        self.present.update([next_loop],0,(720,1280,3))
        self.assertEqual(next_loop["display_bbox"][0],112.)

    def test_symmetric_vehicle_shape_has_no_stable_direction(self):
        self.assertIsNone(visible_major_axis(
            [(0,0),(100,0),(100,100),(0,100)]))

    def test_long_body_reports_undirected_axis_not_heading(self):
        rect = cv2.boxPoints(((120.,110.),(220.,65.),177.))
        axis = visible_major_axis([tuple(x) for x in rect])
        self.assertIsNotNone(axis)
        self.assertGreater(axis[2],200)
        self.assertTrue(0<=axis[3]<3.142)

    def test_mask_area_centroid_normalizes_correctly(self):
        centroid = polygon_area_centroid(
            [(100,100),(300,100),(300,300),(100,300)],(400,800,3))
        self.assertAlmostEqual(centroid[0], .25)
        self.assertAlmostEqual(centroid[1], .50)

    def test_shape_turns_without_changing_raw_bbox(self):
        origin = observation(1,100,100,300,160)
        rotated = observation(1,180,50,240,260)
        before = list(rotated["bbox"])
        self.present.update([origin],0.,(720,1280,3))
        self.present.update([rotated],.2,(720,1280,3))
        self.assertEqual(rotated["bbox"],before)
        self.assertIn("visible_long_axis",rotated)


if __name__ == "__main__":
    unittest.main()
