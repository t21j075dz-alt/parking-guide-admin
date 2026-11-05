# -*- coding: utf-8 -*-
"""Regression tests for conservative video-only parking geometry fusion."""
import unittest

from monitor import inside
from parking_geometry_fusion import ParkingGeometryFusion
from recorded_parking_states import RecordedParkingStateMachine
from vehicle_segmentation import DisplayBoxSmoother


def mask_car(raw=1, uid="a", conf=.95):
    return {
        "track_id": raw,
        "segmentation_contour": [(1, 1), (2, 1), (2, 3)],
        "segmentation_bottom_points": [(i / 10., .7) for i in range(9)],
        "segmentation_candidate": uid,
        "segmentation_touched": [uid],
        "segmentation_confidence": conf,
        "segmentation_match_iou": .93,
    }


class GeometryFusionTests(unittest.TestCase):
    def test_agreement_is_immediate(self):
        result = ParkingGeometryFusion().resolve(mask_car(), "a", {"a"}, 0)
        self.assertEqual(result, ("a", {"a"}, "agreement"))

    def test_conflict_never_selects_a_space(self):
        fusion = ParkingGeometryFusion()
        for t in (0, .5, 1, 2, 3, 4):
            uid, touched, basis = fusion.resolve(mask_car(), "b", {"b"}, t)
            self.assertIsNone(uid)
            self.assertEqual(touched, {"a", "b"})
            self.assertEqual(basis, "conflict")

    def test_mask_only_requires_multiple_frames_and_two_seconds(self):
        fusion = ParkingGeometryFusion()
        for t in (0, .5, 1, 1.5):
            uid, touched, basis = fusion.resolve(mask_car(), None, {"a"}, t)
            self.assertIsNone(uid)
            self.assertEqual(basis, "mask-pending")
        uid, touched, basis = fusion.resolve(mask_car(), None, {"a"}, 2)
        self.assertEqual((uid, basis), ("a", "mask-temporal"))

    def test_mask_only_resets_on_long_gap_or_new_stall(self):
        fusion = ParkingGeometryFusion()
        for t in (0, .5, 1, 1.5):
            fusion.resolve(mask_car(), None, {"a"}, t)
        self.assertEqual(fusion.resolve(mask_car(), None, {"a"}, 3)[2],
                         "mask-pending")
        self.assertEqual(fusion.resolve(mask_car(uid="b"), None, {"b"}, 3.1)[2],
                         "mask-pending")

    def test_low_quality_mask_cannot_authorize_occupancy(self):
        fusion = ParkingGeometryFusion()
        for i in range(20):
            uid, touched, basis = fusion.resolve(
                mask_car(conf=.6), None, {"a"}, i / 10.)
            self.assertIsNone(uid)
            self.assertEqual(basis, "mask-uncertain")

    def test_without_mask_preserves_legacy(self):
        fusion = ParkingGeometryFusion()
        result = fusion.resolve({"track_id": 1}, "a", {"a"}, 0)
        self.assertEqual(result, ("a", {"a"}, "legacy"))

    def test_untracked_car_cannot_vote_via_mask(self):
        fusion = ParkingGeometryFusion()
        for i in range(30):
            uid, _, basis = fusion.resolve(
                mask_car(raw=None), None, {"a"}, i / 10.)
            self.assertIsNone(uid)
            self.assertEqual(basis, "no-track")

    def test_mask_believed_other_stall_not_used_as_fallback(self):
        fusion = ParkingGeometryFusion()
        for i in range(30):
            uid, _, basis = fusion.resolve(
                mask_car(uid="b"), None, {"a"}, i / 10.)
            self.assertIsNone(uid)
            self.assertEqual(basis, "mask-uncertain")

    def test_fusion_recorded_demo_does_not_occupy_on_conflict(self):
        zones = {"a": [[.1,.3],[.49,.3],[.49,.9],[.1,.9]],
                 "b": [[.51,.3],[.9,.3],[.9,.9],[.51,.9]]}
        machine = RecordedParkingStateMachine(zones, geometry_mode="fusion")
        # Legacy bbox selects a, while confident mask says b.
        for n in range(90):
            car = {
                "track_id": 1, "name": "car",
                "bbox": [150, 400, 420, 700],
                "image_size": (1000,1000),
                "confidence": .95, "monitored": True,
                "night_verified": True,
                **mask_car(uid="b"),
            }
            states, phases = machine.update([car],zones,inside,n / 10.)
            self.assertNotEqual(states["a"], "occupied")
            self.assertNotEqual(states["b"], "occupied")

    def test_display_smoothing_does_not_change_original_bbox(self):
        smooth = DisplayBoxSmoother()
        a = {"track_id":1,"bbox":[100,100,200,200]}
        smooth.update([a],0,(500,500,3))
        b = {"track_id":1,"bbox":[110,100,210,200]}
        smooth.update([b],.1,(500,500,3))
        self.assertEqual(b["bbox"],[110,100,210,200])
        self.assertTrue(100 < b["display_bbox"][0] < 110)
        # Large jump: do not drag a stale box across unrelated objects.
        c = {"track_id":1,"bbox":[390,300,490,400]}
        smooth.update([c],.2,(500,500,3))
        self.assertEqual(c["display_bbox"],[390,300,490,400])

    def test_invalid_geometry_mode(self):
        with self.assertRaises(ValueError):
            RecordedParkingStateMachine({"a": []}, geometry_mode="anything")


if __name__ == "__main__":
    unittest.main()
