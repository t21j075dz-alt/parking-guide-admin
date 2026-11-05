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

    def test_confidence_dips_pause_but_do_not_erase_mask_history(self):
        fusion = ParkingGeometryFusion()
        sequence = [
            (0.0, .85), (.2, .84), (.4, .81), (.6, .75),
            (.8, .83), (1.0, .82), (1.2, .74), (1.4, .79),
            (1.6, .86),
        ]
        states = []
        for seconds, confidence in sequence:
            states.append(fusion.resolve(
                mask_car(conf=confidence), None, {"a"}, seconds))
        self.assertEqual(states[3][2], "mask-weak-hold")
        self.assertIsNone(states[3][0])  # weak frame cannot confirm
        self.assertEqual(states[-1][0], "a")
        self.assertEqual(states[-1][2], "mask-temporal")

    def test_agreement_does_not_discard_mask_history(self):
        fusion = ParkingGeometryFusion()
        for t in (0., .2, .4):
            fusion.resolve(mask_car(), None, {"a"}, t)
        self.assertEqual(
            fusion.resolve(mask_car(), "a", {"a"}, .6)[2], "agreement")
        for t in (.8, 1., 1.2, 1.4, 1.6):
            found = fusion.resolve(mask_car(), None, {"a"}, t)
        self.assertEqual(found[0], "a")
        self.assertEqual(found[2], "mask-temporal")

    def test_low_confidence_can_never_start_or_finish_confirmation(self):
        fusion = ParkingGeometryFusion()
        for i in range(25):
            zone, _, basis = fusion.resolve(
                mask_car(conf=.65), None, {"a"}, .1*i)
            self.assertIsNone(zone)
            self.assertEqual(basis, "mask-uncertain")
        self.assertIsNone(
            fusion.resolve(mask_car(), None, {"a"}, 2.5)[0])

    def test_single_stale_positive_does_not_confirm_after_gap(self):
        fusion = ParkingGeometryFusion()
        fusion.resolve(mask_car(), None, {"a"}, 0.)
        for t in (1., 1.2, 1.4, 1.6):
            zone, _, status = fusion.resolve(mask_car(), None, {"a"}, t)
        self.assertIsNone(zone)
        self.assertEqual(status, "mask-pending")

    def test_duplicate_timestamp_does_not_add_positive_frames(self):
        fusion = ParkingGeometryFusion()
        for _ in range(30):
            fusion.resolve(mask_car(), None, {"a"}, 0.)
        out = fusion.resolve(mask_car(), None, {"a"}, 1.6)
        self.assertIsNone(out[0])

    def test_conflicting_zone_clears_prior_positive_evidence(self):
        fusion = ParkingGeometryFusion()
        for t in (0., .2, .4, .6, .8, 1., 1.2):
            fusion.resolve(mask_car(), None, {"a"}, t)
        out = fusion.resolve(mask_car(uid="b"), "a", {"a", "b"}, 1.4)
        self.assertIsNone(out[0])
        self.assertEqual(out[2], "conflict")
        for t in (1.6, 1.8, 2.0):
            result = fusion.resolve(mask_car(), None, {"a"}, t)
            self.assertIsNone(result[0])
            self.assertEqual(result[2], "mask-pending")

    def test_ambiguous_adjacent_space_does_not_flicker_available(self):
        zones = {"a": [[.1,.3],[.49,.3],[.49,.9],[.1,.9]],
                 "b": [[.51,.3],[.9,.3],[.9,.9],[.51,.9]]}
        fusion_demo = RecordedParkingStateMachine(zones, geometry_mode="fusion")

        def uncertain_car():
            return {
                "track_id": 1, "name": "car",
                "bbox": [300, 400, 700, 700],
                "image_size": (1000,1000),
                "confidence": .94,
                "monitored": True, "night_verified": True,
                **mask_car(uid="a"),
            }

        states, _ = fusion_demo.update([uncertain_car()], zones, inside, 0.)
        self.assertEqual(states["b"], "unknown")
        for t in (.3, .6):
            states, _ = fusion_demo.update([], zones, inside, t)
            self.assertEqual(states["b"], "unknown")
        states, _ = fusion_demo.update([uncertain_car()], zones, inside, .7)
        self.assertEqual(states["b"], "unknown")
        for t in (1.0, 1.5):
            states, _ = fusion_demo.update([], zones, inside, t)
            self.assertEqual(states["b"], "unknown")
        states, _ = fusion_demo.update([], zones, inside, 1.8)
        self.assertEqual(states["b"], "available")

    def test_unknown_is_immediate_and_legacy_mode_unchanged(self):
        zones = {"a": [[.1,.3],[.49,.3],[.49,.9],[.1,.9]],
                 "b": [[.51,.3],[.9,.3],[.9,.9],[.51,.9]]}
        legacy = RecordedParkingStateMachine(zones, geometry_mode="legacy")
        bbox = {"track_id":1,"bbox":[300,400,700,700],
                "image_size":(1000,1000),"confidence":.95,
                "monitored":True,"night_verified":True}
        states,_ = legacy.update([bbox], zones, inside, 0.)
        self.assertEqual(states["b"], "unknown")
        states,_ = legacy.update([], zones, inside, .3)
        self.assertEqual(states["b"], "available")

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
