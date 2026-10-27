"""外付けカメラに依存せず、露出調整の安全な動作をテスト。"""
import unittest

from camera_exposure import (
    INITIAL_EXPOSURE, is_valid_manual_exposure,
    set_manual_exposure, step_manual_exposure,
)


class FakeCv2:
    CAP_PROP_AUTO_EXPOSURE = 21
    CAP_PROP_EXPOSURE = 15


class FakeCamera:
    def __init__(self, supported=True, actual_override=None):
        self.supported = supported
        self.actual_override = actual_override
        self.exposure = -7
        self.calls = []

    def set(self, field, value):
        self.calls.append((field, value))
        if field == FakeCv2.CAP_PROP_EXPOSURE:
            if not self.supported:
                return False
            self.exposure = value
        return True

    def get(self, field):
        if self.actual_override is not None:
            return self.actual_override
        return self.exposure


class ExposureTest(unittest.TestCase):
    def test_valid_camera_range(self):
        self.assertTrue(is_valid_manual_exposure(-7))
        self.assertFalse(is_valid_manual_exposure(True))
        self.assertFalse(is_valid_manual_exposure("−7"))
        self.assertFalse(is_valid_manual_exposure(-100))
        self.assertFalse(is_valid_manual_exposure(None))

    def test_darker_means_more_negative(self):
        camera = FakeCamera()
        success, value = step_manual_exposure(camera, FakeCv2, None, -1)
        self.assertTrue(success)
        self.assertEqual(value, INITIAL_EXPOSURE - 1)
        success, value = step_manual_exposure(camera, FakeCv2, value, 1)
        self.assertTrue(success)
        self.assertEqual(value, INITIAL_EXPOSURE)

    def test_unsupported_camera_does_not_falsely_store_exposure(self):
        camera = FakeCamera(supported=False)
        success, value = step_manual_exposure(camera, FakeCv2, None, -1)
        self.assertFalse(success)
        self.assertIsNone(value)

    def test_driver_must_confirm_actual_exposure(self):
        camera = FakeCamera(actual_override=0)
        self.assertFalse(set_manual_exposure(camera, FakeCv2, -7))

    def test_upper_and_lower_bounds_do_not_overflow(self):
        camera = FakeCamera()
        success, value = step_manual_exposure(camera, FakeCv2, 0, 1)
        self.assertTrue(success)
        self.assertEqual(value, 0)
        success, value = step_manual_exposure(camera, FakeCv2, -13, -1)
        self.assertTrue(success)
        self.assertEqual(value, -13)


if __name__ == "__main__":
    unittest.main()
