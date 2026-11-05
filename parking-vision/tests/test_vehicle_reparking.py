"""Regression: an EXITING vehicle must not stay EXITING after parking again.

Uses only the deterministic camera state machine; no GPU / network needed.
"""
import unittest

from monitor import Vehicle


def run(vehicle, points, park_seconds=3.0):
    for seconds, point, zone in points:
        vehicle.observe(point, zone, False, seconds, park_seconds)
    return vehicle.phase


def parked_in_first_stall(vehicle):
    # The same physical car enters from outside the monitored spots.
    points = [(0.0, (.10, .70), None)]
    points.extend((float(t), (.22, .70), "space_006")
                  for t in range(1, 16))
    assert run(vehicle, points) == "parked"
    assert vehicle.space_uid == "space_006"


def leave_first_stall(vehicle):
    # Some moving observations outside the original stall are required to
    # demonstrate departure; a lost ID alone must not produce EXITING.
    moving = [(float(t), (.30 + .07 * (t-16), .70), None)
              for t in range(16, 23)]
    run(vehicle, moving)
    assert vehicle.phase == "exiting"


class ReparkStateTests(unittest.TestCase):
    def test_same_stable_id_may_park_in_new_space_after_exiting(self):
        v = Vehicle("camera", "facility", 1)
        parked_in_first_stall(v)
        leave_first_stall(v)
        # Vehicle traverses zone B with the SAME stable ID.
        run(v, [(float(t), (.74, .71), "space_003")
                for t in range(23, 40)])
        self.assertEqual(v.phase, "parked")
        self.assertEqual(v.space_uid, "space_003")
        self.assertEqual(v.track_id, 1)
        self.assertIsNone(v.left_space_at)
        self.assertEqual(v.outside_since, 0.)

    def test_passing_another_stall_without_stopping_does_not_park(self):
        v = Vehicle("camera", "facility", 1)
        parked_in_first_stall(v)
        leave_first_stall(v)
        # Keeps moving: several stall votes alone do not prove parking.
        path = [(float(t), (.57 + .035*(t-23), .72), "space_003")
                for t in range(23, 28)]
        run(v, path)
        self.assertEqual(v.phase, "exiting")
        self.assertEqual(v.space_uid, "space_006")

    def test_lost_detection_is_not_a_new_parking_event(self):
        v = Vehicle("camera", "facility", 1)
        parked_in_first_stall(v)
        leave_first_stall(v)
        # Without new observations no state change happens.
        self.assertEqual(v.phase, "exiting")

    def test_confirmed_vehicle_exit_still_ends_session(self):
        v = Vehicle("camera", "facility", 1)
        parked_in_first_stall(v)
        leave_first_stall(v)
        v.observe((.86,.72), None, True, 23., 3.0)
        self.assertEqual(v.phase, "exited")


if __name__ == "__main__":
    unittest.main()
