"""Regression for the Nov 9, 2026 600s video: vehicle EXITING while stall STOPPED.

No GPU, network, private footage or camera needed. The independent recorded
stall state already verified the stopped owner; this merely reconciles the
vehicle's displayed/session phase, not the stall's occupancy decision.
"""
import unittest
from types import SimpleNamespace

from monitor import Vehicle, VehicleTracker, inside
from recorded_parking_states import StallProgress, RecordedParkingStateMachine
from reconcile_video_reparking import reconcile_confirmed_video_reparking


def detection(tid, stall_uid, *, stopped=True, verified=True, conf=.96):
    return {"track_id": tid, "demo_zone": stall_uid,
            "demo_stopped": stopped, "night_verified": verified,
            "monitored": True, "confidence": conf,
            "point": (.28, .74)}


def scenario(previous="space_003", now=495.6, current="space_001"):
    car = Vehicle("camera-01", "facility-01", 1, phase="exiting",
                  space_uid=previous, park_anchor=(.6, .7),
                  left_space_at="2026-11-09T08:17:00+00:00",
                  outside_since=450., outside_started_at="earlier")
    car.seen_monotonic = now
    tracker = SimpleNamespace(vehicles={1: car})
    recorded = SimpleNamespace(stalls={
        current: StallProgress(phase="stopped", track_id=1),
    })
    return car, tracker, recorded


class ReconcileRecordedReparkingTests(unittest.TestCase):
    def test_nov9_space1_then_space3_repark_recovers_same_id(self):
        # 495.6s: recorded 1st stall STOPPED but vehicle was still EXITING.
        car, tracker, recorded = scenario()
        original_session_id = car.session_id
        self.assertEqual(car.phase, "exiting")
        observations = detection(1, "space_001")
        events = reconcile_confirmed_video_reparking(
            tracker, recorded, [observations], 495.6)
        self.assertEqual(len(events), 1)
        self.assertEqual(car.phase, "parked")
        self.assertEqual(car.space_uid, "space_001")
        self.assertEqual(car.track_id, 1)
        self.assertEqual(car.session_id, original_session_id)
        self.assertEqual(events[0]["phase"], "parked")
        self.assertIsNotNone(car.parked_at)
        self.assertIsNone(car.left_space_at)
        self.assertEqual(car.outside_since, 0.)
        self.assertTrue(observations["repark_confirmed_by_recorded_stall"])

        # 587.0s: after positively leaving space 1, same ID stops at space 3.
        car.phase = "exiting"
        car.seen_monotonic = 587.
        car.left_space_at = "2026-11-09T08:22:00+00:00"
        recorded.stalls = {"space_003": StallProgress(phase="stopped", track_id=1)}
        events = reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_003")], 587.)
        self.assertEqual(len(events), 1)
        self.assertEqual(car.phase, "parked")
        self.assertEqual(car.space_uid, "space_003")
        self.assertEqual(car.session_id, original_session_id)

    def test_real_recorded_stall_machine_fills_missing_monitor_zone(self):
        # Reproduce the November 9 failure mechanism: a continuously tracked
        # car is physically inside stall 1, but the live zone_candidate is None.
        zones = {"space_001": [[0., .2], [.45, .2], [.45, .8], [0., .8]],
                 "space_002": [[.55, .2], [1., .2], [1., .8], [.55, .8]]}
        tracker = VehicleTracker("facility-01", "camera-01", park_seconds=5)
        car = Vehicle("camera-01", "facility-01", 1, phase="exiting",
                      space_uid="space_002", park_anchor=(.7, .48))
        tracker.vehicles[1] = car
        machine = RecordedParkingStateMachine(zones)
        events_seen = []
        for t in range(8):
            d = {
                "track_id": 1, "confidence": .96, "monitored": True,
                "night_verified": True, "zone_candidate": None,
                "point": (.20, .48), "bbox": (100, 100, 300, 500),
                "image_size": (1000, 1000)
            }
            tracker.update([d], zones, [], float(t))
            statuses, demo_phases = machine.update([d], zones, inside, float(t))
            updates = reconcile_confirmed_video_reparking(
                tracker, machine, [d], float(t))
            events_seen.extend(updates)
            if t < 5:
                self.assertNotEqual(car.phase, "parked")
            if t >= 5:
                self.assertEqual(statuses["space_001"], "occupied")
                self.assertEqual(demo_phases["space_001"], "stopped")
                self.assertEqual(car.phase, "parked")
        self.assertEqual(len(events_seen), 1)
        self.assertEqual(events_seen[0]["space_uid"], "space_001")

    def test_moving_second_car_prevents_unjustified_repark(self):
        car, tracker, recorded = scenario()
        another = detection(2, "space_001", stopped=False)
        another["point"] = (.3, .72)
        events = reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_001"), another], 495.6)
        self.assertEqual(events, [])
        self.assertEqual(car.phase, "exiting")

    def test_same_stall_return_allowed_only_after_stopped(self):
        car, tracker, recorded = scenario(previous="space_001")
        events = reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_001")], 495.6)
        self.assertEqual(len(events), 1)
        self.assertEqual(car.phase, "parked")

    def test_unconfirmed_or_driving_vehicle_is_never_reparked(self):
        for invalid in (
            {"stopped": False}, {"verified": False}, {"conf": .15},
            {"tid": 2}, {"stall_uid": "space_002"}
        ):
            with self.subTest(invalid=invalid):
                car, tracker, recorded = scenario()
                payload = {"tid": 1, "stall_uid": "space_001", **invalid}
                d = detection(payload["tid"], payload["stall_uid"],
                              stopped=payload.get("stopped", True),
                              verified=payload.get("verified", True),
                              conf=payload.get("conf", .96))
                events = reconcile_confirmed_video_reparking(
                    tracker, recorded, [d], 495.6)
                self.assertEqual(events, [])
                self.assertEqual(car.phase, "exiting")

    def test_occupied_but_not_stopped_is_not_evidence(self):
        for phase in ("available", "unknown", "parking_in", "exiting"):
            with self.subTest(phase=phase):
                car, tracker, recorded = scenario()
                recorded.stalls["space_001"].phase = phase
                events = reconcile_confirmed_video_reparking(
                    tracker, recorded, [detection(1, "space_001")], 495.6)
                self.assertEqual(events, [])
                self.assertEqual(car.phase, "exiting")

    def test_stale_track_or_wrong_stall_owner_is_not_reparked(self):
        car, tracker, recorded = scenario()
        car.seen_monotonic = 480.
        self.assertFalse(reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_001")], 495.6))
        car.seen_monotonic = 495.6
        recorded.stalls["space_001"].track_id = 55
        self.assertFalse(reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_001")], 495.6))
        self.assertEqual(car.phase, "exiting")

    def test_two_cars_claiming_stall_are_ambiguous(self):
        car, tracker, recorded = scenario()
        car2 = Vehicle("camera-01", "facility-01", 2, phase="exiting",
                       space_uid="space_006")
        car2.seen_monotonic = 495.6
        tracker.vehicles[2] = car2
        events = reconcile_confirmed_video_reparking(
            tracker, recorded,
            [detection(1, "space_001"), detection(2, "space_001")], 495.6)
        self.assertEqual(events, [])
        self.assertEqual(car.phase, "exiting")

    def test_existing_parked_vehicle_blocks_conflicting_claim(self):
        car, tracker, recorded = scenario()
        other = Vehicle("camera-01", "facility-01", 3, phase="parked",
                        space_uid="space_001")
        tracker.vehicles[3] = other
        self.assertFalse(reconcile_confirmed_video_reparking(
            tracker, recorded, [detection(1, "space_001")], 495.6))
        self.assertEqual(car.phase, "exiting")

    def test_does_not_override_other_phases_or_change_stall(self):
        for phase in ("entering", "moving", "parked", "exited"):
            with self.subTest(phase=phase):
                car, tracker, recorded = scenario()
                car.phase = phase
                prior = recorded.stalls["space_001"].phase
                self.assertFalse(reconcile_confirmed_video_reparking(
                    tracker, recorded, [detection(1, "space_001")], 495.6))
                self.assertEqual(car.phase, phase)
                self.assertEqual(recorded.stalls["space_001"].phase, prior)


if __name__ == "__main__":
    unittest.main()
