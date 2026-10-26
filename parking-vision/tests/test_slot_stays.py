"""車が長時間止まっている間はYOLO生ID変更では駐車IDを変えない。"""
import unittest
from slot_stays import SlotStayManager, color_shape
from admin_layout import extract, verify


ZONES = {"space_001": [[0,0],[0.5,0],[0.5,0.5],[0,0.5]]}


def car(raw, x=.25, y=.25, name="car"):
    return {"name":name, "track_id":raw, "point":(x,y),
            "bottom_points":[(x-.01,y),(x,y),(x+.01,y)],
            "bbox":[200,150,400,300], "confidence":.80}


class SlotAnchoredTests(unittest.TestCase):
    def test_id_is_constant_after_stopping_despite_yolo_reassignments(self):
        manager = SlotStayManager("home-test-001", "home-cam", ZONES, park_seconds=3)
        events = []
        for second in range(25):
            events.extend(manager.update(
                [car(raw=second+1, name="van" if second%2 else "car")],
                {"space_001":"occupied"}, float(second)))
        self.assertEqual(len([e for e in events if e["event"] == "parked"]), 1)
        self.assertEqual(len(manager.active), 1)
        stay = manager.active["space_001"]
        self.assertEqual(stay.camera_number, 1000000)
        self.assertIsNone(stay.park_start_video)  # already present at video start
        first_session = stay.session_id
        manager.update([], {"space_001":"unknown"}, 25.0)
        self.assertEqual(manager.active["space_001"].session_id, first_session)
        self.assertEqual(manager.active["space_001"].visibility, "lost")
        manager.update([car(500, name="car")], {"space_001":"occupied"}, 30.0)
        self.assertEqual(manager.active["space_001"].session_id, first_session)
        self.assertEqual(manager.active["space_001"].camera_number, 1000000)

    def test_after_known_vacancy_new_car_duration_is_measurable(self):
        manager = SlotStayManager(
            "home-test-001", "camera", ZONES, park_seconds=2,
            confirmed_initially_empty=["space_001"])
        manager.update([], {"space_001":"available"}, 0)
        for t in (1,2,3,4):
            manager.update([car(t)], {"space_001":"occupied"}, float(t))
        self.assertIn("space_001", manager.active)
        self.assertEqual(manager.active["space_001"].park_start_video, 1.0)
        shown = manager.current_display(5)[0]
        self.assertEqual(shown["duration_seconds"], 4)
        self.assertTrue(shown["started_at_observed"])

    def test_occluded_stay_survives_and_exits_only_after_verified_empty(self):
        manager = SlotStayManager(
            "home-test-001", "camera", ZONES, park_seconds=1,
            blind_uids=["space_001"])
        for t in (0,1,2):
            manager.update([car(t)], {"space_001":"occupied"}, float(t))
        stay_id = manager.active["space_001"].session_id
        manager.update([], {"space_001":"unknown"}, 3, departures=["space_001"])
        self.assertEqual(manager.active["space_001"].session_id, stay_id)
        self.assertEqual(manager.active["space_001"].visibility, "occluded")
        manager.update([], {"space_001":"available"}, 20)
        self.assertEqual(manager.active["space_001"].session_id, stay_id)

    def test_departure_then_new_car_creates_new_session(self):
        manager = SlotStayManager("home-test-001", "cam", ZONES, park_seconds=1,
                                  confirmed_initially_empty=["space_001"])
        manager.update([], {"space_001":"available"}, 0)
        for t in (1,2,3): manager.update([car(t)], {"space_001":"occupied"}, t)
        old = manager.active["space_001"].session_id
        manager.update([], {"space_001":"unknown"}, 4, departures=["space_001"])
        manager.update([], {"space_001":"available"}, 10)
        self.assertNotIn("space_001", manager.active)
        for t in (12,13,14): manager.update([car(900+t)], {"space_001":"occupied"}, t)
        self.assertNotEqual(manager.active["space_001"].session_id, old)

    def test_two_zones_have_distinct_slot_ids(self):
        zones = {
            "space_001":[[0,0],[.5,0],[.5,.5],[0,.5]],
            "space_002":[[.5,0],[1,0],[1,.5],[.5,.5]]}
        manager = SlotStayManager("home-test-001","cam",zones,park_seconds=1)
        for t in (0,1,2):
            manager.update([car(t,.25,.25),car(100+t,.75,.25)],
                           {"space_001":"occupied","space_002":"occupied"},t)
        self.assertEqual(len(manager.active),2)
        self.assertEqual(len({s.camera_number for s in manager.active.values()}),2)

    def test_color_shape_unknown_without_frame(self):
        self.assertEqual(color_shape(None, car(1)), ("不明", 1.33))


class AdminLayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = {
            "facilityId":"home-test-001",
            "objects":[
                {"objectType":"parkingSpace","uid":"space_001","spaceNumber":"1",
                 "spaceType":"accessible","x":50,"y":80},
                {"objectType":"parkingLot","uid":"lot_1"},
            ],
        }

    def test_admin_uid_matches_camera_geometry_only_by_uid(self):
        result=verify(self.layout,"home-test-001",["space_001"])
        self.assertEqual(result["space_001"]["space_type"],"accessible")
        self.assertNotIn("x",result["space_001"])

    def test_other_facility_or_missing_spot_fails(self):
        with self.assertRaises(ValueError):
            verify(self.layout,"nikko-test-001",["space_001"])
        with self.assertRaises(ValueError):
            verify(self.layout,"home-test-001",["space_999"])

    def test_export_collection_matches(self):
        result=extract({"home-test-001":self.layout},"home-test-001")
        self.assertIn("space_001",result)


if __name__=="__main__":
    unittest.main()
