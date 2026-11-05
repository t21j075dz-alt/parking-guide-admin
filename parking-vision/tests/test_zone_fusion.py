# -*- coding: utf-8 -*-
"""Safety tests for parking-zone decisions from multiple imperfect cues."""
import unittest

from monitor import inside
from zone_fusion import TemporalZoneFusion
from recorded_parking_states import RecordedParkingStateMachine


LEFT = [[.1,.2],[.48,.2],[.48,.9],[.1,.9]]
RIGHT = [[.52,.2],[.9,.2],[.9,.9],[.52,.9]]


def observation(track_id=1, box=(200,400,420,710),
                mask_zone="left", mask_touched=("left",),
                mask_confidence=.91, mask_iou=.95):
    return {
        "name": "car", "track_id": track_id,
        "bbox": list(box), "image_size": (1000,1000),
        "confidence": .94, "point": ((box[0]+box[2])/2000, box[3]/1000),
        "monitored": True, "night_verified": True,
        "segmentation_contour": [[200,400],[420,400],[420,710],[200,710]],
        "segmentation_bottom_points": [(.20+i*.01,.71) for i in range(9)],
        "segmentation_candidate": mask_zone,
        "segmentation_touched": list(mask_touched),
        "segmentation_confidence": mask_confidence,
        "segmentation_match_iou": mask_iou,
    }


class ZoneFusionTests(unittest.TestCase):
    def setUp(self):
        self.zones = {"left": LEFT, "right": RIGHT}
        self.fusion = TemporalZoneFusion()

    def at(self, time_s, det):
        return self.fusion.update([det], self.zones, inside, time_s)[0]

    def test_two_independent_cues_agree(self):
        data = self.at(0, observation())
        self.assertEqual(data["fused_zone_candidate"], "left")
        self.assertEqual(data["fused_zone_basis"], "bbox+mask")
        self.assertFalse(data["fused_zone_conflict"])

    def test_mask_alone_repeatedly_can_recover_ambiguous_box(self):
        # This recreates 171.8-173.6 seconds of the real video:
        # the rectangular bottom has no single zone while the mask does.
        choices = []
        for index in range(18):
            det = observation(box=(410,400,605,710))
            choices.append(self.at(index*.1, det)["fused_zone_candidate"])
        self.assertTrue(all(x is None for x in choices[:12]))
        self.assertEqual(choices[-1], "left")

    def test_frame_gap_resets_tentative_confirmation(self):
        for t in (0., .1, .2, .3):
            self.at(t, observation(box=(410,400,605,710)))
        result = self.at(2.0, observation(box=(410,400,605,710)))
        self.assertIsNone(result["fused_zone_candidate"])

    def test_conflicting_evidence_is_unknown_not_occupied(self):
        data = self.at(0, observation(mask_zone="right",
                                      mask_touched=("right",)))
        self.assertTrue(data["fused_zone_conflict"])
        self.assertIsNone(data["fused_zone_candidate"])
        self.assertEqual(set(data["fused_zone_touched"]),
                         {"left","right"})

    def test_weak_mask_is_not_considered_ground_evidence(self):
        data = self.at(0, observation(mask_zone="right",
                                      mask_touched=("right",),
                                      mask_confidence=.2))
        self.assertFalse(data["fused_zone_conflict"])
        self.assertIsNone(data["fused_zone_candidate"])
        self.assertEqual(data["fused_zone_basis"], "bbox-only")
        self.assertEqual(data["fused_zone_touched"], ["left"])

    def test_missing_track_id_cannot_confirm_single_cue(self):
        candidate = None
        for i in range(25):
            candidate = self.at(i*.1, observation(
                track_id=None, box=(410,400,605,710)))["fused_zone_candidate"]
        self.assertIsNone(candidate)

    def test_two_tracks_are_kept_independent(self):
        self.at(0, observation(track_id=1,box=(410,400,605,710)))
        result = self.at(.5, observation(track_id=2,box=(410,400,605,710)))
        self.assertIsNone(result["fused_zone_candidate"])
        self.assertEqual(self.fusion.pending[2].frames,1)

    def test_reset_clears_prior_video_loop(self):
        for i in range(15):
            self.at(i*.1, observation(box=(410,400,605,710)))
        self.fusion.reset()
        result = self.at(0,observation(box=(410,400,605,710)))
        self.assertIsNone(result["fused_zone_candidate"])

    def test_conflict_does_not_make_neighbor_occupied(self):
        model = RecordedParkingStateMachine(self.zones)
        for clock in (0,1,2,3,4,5,6):
            det=self.at(clock,observation(mask_zone="right",
                                          mask_touched=("right",)))
            states,phases=model.update([det],self.zones,inside,float(clock))
        self.assertNotEqual(states["left"], "occupied")
        self.assertNotEqual(states["right"], "occupied")

    def test_confirmed_mask_only_needs_downstream_five_seconds(self):
        model=RecordedParkingStateMachine(self.zones)
        # geometry remains undecided on the rectangle all the time;
        # persistent mask candidate can prove which zone but the 5-second
        # occupancy confirmation delay still applies.
        for n in range(75):
            t=n*.1
            det=self.at(t,observation(box=(410,400,605,710)))
            states,phases=model.update([det],self.zones,inside,t)
            if t < 5.0:
                self.assertNotEqual(states["left"], "occupied")
        self.assertEqual(phases["left"], "stopped")
        self.assertEqual(states["right"], "available")

    def test_mask_motion_point_avoids_false_motion_from_turning_box(self):
        model=RecordedParkingStateMachine({"left":LEFT})
        for t in range(0,9):
            # The bottom of the bbox changes by 60px in a turn, but
            # the mask centre stays stable. This is not ground contact,
            # merely a better proxy for translational motion.
            box=(200,400,420,650 if t % 2 else 710)
            det=observation(box=box)
            det["motion_point"]=(.31,.54)
            states,phases=model.update([det],{"left":LEFT},inside,float(t))
        self.assertEqual(phases["left"], "stopped")


if __name__ == "__main__":
    unittest.main()
