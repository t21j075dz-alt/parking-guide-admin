"""Photo-only startup does not require a model, calibration or saved credentials."""
import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

import publish_camera


class PhotoStartupTests(unittest.TestCase):
    def setup_camera(self, keys):
        camera = Mock()
        camera.isOpened.return_value = True
        camera.read.return_value = (True, SimpleNamespace(shape=(720, 1280, 3)))
        cv2 = Mock()
        cv2.waitKey.side_effect = keys
        return camera, cv2

    def test_default_is_private_and_uses_the_existing_public_configuration(self):
        config = publish_camera.settings(1, "home-test-001")
        self.assertTrue(config["camera_snapshots_enabled"])
        self.assertFalse(config["public_snapshots_enabled"])
        self.assertEqual(config["supabase_url"], "https://gahoqlpuufqjqpyaaykt.supabase.co")
        with self.assertRaises(ValueError):
            publish_camera.settings(-1, "home-test-001")

    def test_quitting_confirmation_never_logs_in_or_publishes(self):
        camera, cv2 = self.setup_camera([ord("q")])
        with patch.dict("sys.modules", {"cv2": cv2}), patch.object(publish_camera, "open_camera", return_value=camera), patch.object(publish_camera, "SupabaseWriter") as writer, patch("sys.argv", ["publish_camera.py", "--camera", "1"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                publish_camera.main()
        writer.assert_not_called()
        camera.release.assert_called_once()
        cv2.destroyAllWindows.assert_called_once()

    def test_public_opt_in_and_no_model_or_calibration_required(self):
        camera, cv2 = self.setup_camera([ord("y"), ord("q")])
        output = io.StringIO()
        with patch.dict("sys.modules", {"cv2": cv2}), patch.object(publish_camera, "open_camera", return_value=camera), patch.object(publish_camera, "SupabaseWriter") as writer, patch.object(publish_camera, "SnapshotPublisher") as publisher, patch.object(publish_camera, "getpass", return_value="test-password"), patch("sys.argv", ["publish_camera.py", "--camera", "1", "--email", "operator@example.test", "--public"]), contextlib.redirect_stdout(output):
            publish_camera.main()
        config = publisher.call_args.args[1]
        self.assertTrue(config["public_snapshots_enabled"])
        self.assertNotIn("vehicle_model", config)
        self.assertNotIn("space_zones", config)
        publisher.return_value.publish.assert_called_once()
        self.assertNotIn("test-password", output.getvalue())
        camera.release.assert_called_once()

    def test_login_failure_releases_the_camera(self):
        camera, cv2 = self.setup_camera([ord("y")])
        with patch.dict("sys.modules", {"cv2": cv2}), patch.object(publish_camera, "open_camera", return_value=camera), patch.object(publish_camera, "SupabaseWriter", side_effect=URLError("offline")), patch.object(publish_camera, "getpass", return_value="test-password"), patch("sys.argv", ["publish_camera.py", "--camera", "1", "--email", "operator@example.test"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(URLError):
                publish_camera.main()
        camera.release.assert_called_once()
