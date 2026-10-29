"""Operator-verified empty stalls stay distinct from inferred availability."""
import time
import unittest

from confirm_initial_empty import choose_verified_empty, read_labels
from monitor import SpaceObserver


class VerifiedEmptyTest(unittest.TestCase):
    def setUp(self):
        self.config = {
            "facility_id": "home-test-001",
            "space_uids": ["space_001", "space_002", "space_003",
                           "space_004", "space_005", "space_006"],
            "space_zones": {
                f"space_{i:03}": [[.01,.1],[.09,.1],[.09,.9],[.01,.9]]
                for i in range(1,7)
            },
        }

    def test_operator_choices_are_exact_registered_uids(self):
        self.assertEqual(choose_verified_empty(self.config, "3,6"),
                         ["space_003", "space_006"])
        self.assertEqual(choose_verified_empty(self.config, ""), [])
        self.assertEqual(choose_verified_empty(self.config, "3、6、3"),
                         ["space_003", "space_006"])

    def test_reject_unregistered_or_uncalibrated_stalls(self):
        with self.assertRaises(ValueError):
            choose_verified_empty(self.config, "7")
        with self.assertRaises(ValueError):
            choose_verified_empty(self.config, "abc")
        self.config["space_zones"].pop("space_006")
        with self.assertRaises(ValueError):
            choose_verified_empty(self.config, "3")

    def test_fresh_approval_can_make_only_checked_space_available(self):
        observer = SpaceObserver(
            ["space_003", "space_006"],
            initially_confirmed_empty_uids=["space_003"],
            initial_empty_deadline_epoch=time.time() + 500,
        )
        result = {"space_003": "available", "space_006": "available"}
        observer.update(result, 0)
        status = observer.update(result, 6)
        self.assertEqual(status["space_003"], "available")
        self.assertEqual(status["space_006"], "unknown")

    def test_expired_approval_revokes_previous_available_status(self):
        observer = SpaceObserver(["space_003"],
            initially_confirmed_empty_uids=["space_003"],
            initial_empty_deadline_epoch=time.time() + 500)
        observer.update({"space_003": "available"}, 0)
        self.assertEqual(observer.update({"space_003": "available"}, 6)["space_003"], "available")
        observer.initial_empty_deadline_epoch = time.time() - 5
        observer.update({"space_003": "available"}, 7)
        self.assertEqual(observer.update({"space_003": "available"}, 8)["space_003"], "unknown")


if __name__ == "__main__":
    unittest.main()
