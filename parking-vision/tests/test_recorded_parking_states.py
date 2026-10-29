"""録画実演の区画判定: 5秒と移動を検証する（GPU・Supabase不使用）。"""
import unittest

from monitor import inside
from recorded_parking_states import (
    RecordedParkingStateMachine, bottom_footprint_candidate,
    STATUS_FOR_PHASE,
)


def detection(tid, box, width=1000, height=1000, confidence=.94):
    return {
        "track_id": tid,
        "bbox": box,
        "image_size": (width, height),
        "confidence": confidence,
        "monitored": True,
        "night_verified": True,
    }


class DemoParkingStateTests(unittest.TestCase):
    def setUp(self):
        self.zones = {"space_001": [[.25,.4],[.60,.4],[.60,.85],[.25,.85]],
                      "space_002": [[.62,.4],[.90,.4],[.90,.85],[.62,.85]]}
        self.machine = RecordedParkingStateMachine(self.zones)

    def update(self, sec, boxes):
        return self.machine.update(
            boxes, self.zones, inside, sec
        )

    def test_starts_free_only_for_recorded_demo(self):
        statuses, phases = self.update(0, [])
        self.assertEqual(statuses["space_001"], "available")
        self.assertEqual(phases["space_001"], "available")
        self.assertEqual(statuses["space_002"], "available")

    def test_five_seconds_of_bottom_overlap_then_parking_and_stopping(self):
        # A vehicle moves along the parking space for six seconds.
        for sec, x in [(0, 300),(2, 315),(4, 331)]:
            statuses, phases = self.update(sec, [
                detection(7,(x,400,x+190,700))
            ])
            self.assertNotEqual(statuses["space_001"], "occupied")
        statuses, phases = self.update(6, [
            detection(7,(345,400,535,700))
        ])
        self.assertEqual(phases["space_001"], "parking_in")
        self.assertEqual(statuses["space_001"], "occupied")
        # Then remain within the space for >5 seconds with only box jitter.
        for sec, x in [(8,345),(10,345),(12,346),(14,345)]:
            statuses, phases = self.update(sec, [detection(7,(x,400,x+190,700))])
        self.assertEqual(phases["space_001"], "stopped")

    def test_stationary_car_already_visible_at_video_start(self):
        # Existing car should be detected as STOPPED, rather than fake movement.
        for sec in (0,2,4):
            statuses, phases = self.update(sec, [
                detection(1,(300,400,490,700))
            ])
            self.assertEqual(statuses["space_001"], "unknown")
        statuses, phases = self.update(6, [detection(1,(300,400,490,700))])
        self.assertEqual(phases["space_001"], "stopped")
        self.assertEqual(statuses["space_001"], "occupied")

    def test_exiting_requires_positive_movement_out_of_stall(self):
        for sec in (0,2,4,6,8):
            self.update(sec,[detection(1,(300,400,490,700))])
        # Losing the car temporarily is not evidence of a departure.
        statuses, phases = self.update(10, [])
        self.assertEqual(phases["space_001"], "stopped")
        # Same tracked car now moves outside the stall.
        self.update(12,[detection(1,(760,400,940,700))])
        self.update(13,[detection(1,(780,400,960,700))])
        statuses, phases = self.update(14,[detection(1,(800,400,980,700))])
        self.assertEqual(phases["space_001"], "exiting")
        self.assertEqual(statuses["space_001"], "occupied")
        statuses, phases = self.update(15,[detection(1,(820,400,995,700))])
        self.assertEqual(phases["space_001"], "available")
        self.assertEqual(statuses["space_001"], "available")

    def test_confirmed_exit_can_complete_after_car_leaves_monitor_region(self):
        for sec in (0,2,4,6,8):
            self.update(sec,[detection(1,(300,400,490,700))])
        self.update(12,[detection(1,(760,400,940,700))])
        self.update(13,[detection(1,(780,400,960,700))])
        _, phases = self.update(14,[detection(1,(800,400,980,700))])
        self.assertEqual(phases["space_001"], "exiting")
        # Once positively observed outside, monitor-area filtering can lose it.
        statuses, phases = self.update(16,[])
        self.assertEqual(phases["space_001"], "available")
        self.assertEqual(statuses["space_001"], "available")

    def test_no_automatic_free_after_track_vanishes(self):
        for sec in (0,2,4,6):
            self.update(sec,[detection(1,(300,400,490,700))])
        for sec in (8,10,12,20,30):
            statuses, phases = self.update(sec,[])
            self.assertEqual(phases["space_001"], "stopped")
            self.assertEqual(statuses["space_001"], "occupied")

    def test_short_spurious_overlap_never_occupies(self):
        self.update(0,[detection(1,(300,400,490,700))])
        self.update(1,[])
        statuses, phases = self.update(4,[])
        self.assertEqual(phases["space_001"], "available")
        self.assertEqual(statuses["space_001"], "available")

    def test_ambiguous_neighbor_is_not_automatically_occupied(self):
        zones = {
            "space_003": [[.395,.616],[.524,.616],[.621,.622],
                          [.457,.764],[.395,.745]],
            "space_004": [[.6175,.63556],[.49333,.74074],
                          [.58583,.78222],[.70917,.6637]],
        }
        # Grounded in an observed box at 20:36:53 in user diagnostic CSV.
        # Prefer a stable single stall or uncertainty to "occupy" both.
        detected = detection(3,(532,375,766,525),1280,720)
        uid, touched, _ = bottom_footprint_candidate(detected,zones,inside)
        self.assertNotEqual(uid,"space_004")
        self.assertIn("space_003",touched)

    def test_real_six_stalls_diagonal_parking_3_versus_4(self):
        # Calibrated polygons from 2026-10-29 laptop camera (1280x720).
        # In user's reanalysis, underbody counted 13/13 in these two
        # neighboring spaces for roughly 280 seconds, but center of car
        # footprint is much nearer the center of space_003.
        zones = {
            "space_003": [
                [.52417,.61630],[.39500,.74519],
                [.45667,.76444],[.62083,.62222],
            ],
            "space_004": [
                [.61750,.63556],[.49333,.74074],
                [.58583,.78222],[.70917,.66370],
            ],
        }
        vehicle = detection(3, (530,374,770,527), 1280,720)
        chosen, touched, anchor = bottom_footprint_candidate(
            vehicle,zones,inside)
        self.assertEqual(chosen,"space_003")
        self.assertIn("space_004",touched)
        self.assertIn("space_003",touched)
        demo = RecordedParkingStateMachine(zones)
        for clock in (0,1,2,3,4):
            status,phase = demo.update([detection(3,(530,374,770,527),1280,720)],
                                       zones,inside,float(clock))
            self.assertNotEqual(status["space_004"],"occupied")
        status, phase = demo.update([detection(3,(530,374,770,527),1280,720)],
                                    zones,inside,5.1)
        self.assertEqual(phase["space_003"],"stopped")
        self.assertEqual(status["space_003"],"occupied")
        self.assertEqual(status["space_004"],"available")

    def test_actual_equal_distance_remains_unknown(self):
        zones={"a":[[.1,.3],[.49,.3],[.49,.9],[.1,.9]],
               "b":[[.51,.3],[.9,.3],[.9,.9],[.51,.9]]}
        box=detection(6,(300,300,700,700),1000,1000)
        chosen, touched, anchor = bottom_footprint_candidate(box,zones,inside)
        self.assertIsNone(chosen)

    def test_recorded_frame_clock_never_runs_backward(self):
        self.update(6,[])
        with self.assertRaisesRegex(ValueError,"逆行"):
            self.update(5,[])


if __name__ == "__main__":
    unittest.main()
