# -*- coding: utf-8 -*-
"""No hardware/GPU is required for the safety-warning logic tests."""
import unittest
from traffic_safety import CrowdSafetyMonitor


def detect(name, x=.5, y=.5, conf=.9, box=None):
    return {"name": name, "point": (x, y), "confidence": conf,
            "bbox": box or [x * 100, y * 100, x * 100 + 5, y * 100 + 5]}


class CrowdSafetyTests(unittest.TestCase):
    def make_monitor(self, **kwargs):
        return CrowdSafetyMonitor(spaces={"s1": [[.2, .2], [.8, .2], [.8, .8], [.2, .8]]},
                                  **kwargs)

    def test_sustained_pedestrians(self):
        monitor = self.make_monitor()
        people = [detect("person", x) for x in (.3, .4, .5)]
        self.assertFalse(monitor.observe([], people, now=0)["pedestrian_warning"])
        self.assertFalse(monitor.observe([], people, now=1)["pedestrian_warning"])
        self.assertTrue(monitor.observe([], people, now=2.1)["pedestrian_warning"])
        self.assertTrue(monitor.observe([], [], now=3)["pedestrian_warning"])
        self.assertFalse(monitor.observe([], [], now=8.1)["pedestrian_warning"])

    def test_bicycles_and_ignored_people(self):
        monitor = self.make_monitor()
        bikes = [detect("bicycle", .4), detect("bicycle", .6)]
        self.assertFalse(monitor.observe(bikes, [], now=4)["bicycle_warning"])
        self.assertTrue(monitor.observe(bikes, [], now=6.1)["bicycle_warning"])
        self.assertEqual(monitor.observe(bikes, [detect("person", .01, .01)], now=7)
                         ["pedestrian_count"], 0)

    def test_duplicate_detections_and_confidence(self):
        monitor = self.make_monitor()
        people = [detect("person", .5, .5, box=[20, 20, 90, 90]),
                  detect("person", .5, .5, box=[22, 22, 88, 88]),
                  detect("person", .6, .6, conf=.1)]
        self.assertEqual(monitor.observe([], people, now=1)["pedestrian_count"], 1)

    def test_area_override(self):
        monitor = self.make_monitor(monitor_zone=[[.7,.7],[.9,.7],[.9,.9],[.7,.9]])
        self.assertEqual(monitor.observe([], [detect("person",.3,.3)], now=1)
                         ["pedestrian_count"], 0)


if __name__ == "__main__":
    unittest.main()
