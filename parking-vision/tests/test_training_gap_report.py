"""Read-only gap report for existing annotation tasks and new layout classes."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from training_gap_report import build_report
from unified_annotation_dataset import AnnotationWorkspace, layout_polygon_to_yolo


class GapReportTests(unittest.TestCase):
    def test_unreviewed_is_not_negative_and_counts_are_task_separated(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            imgs = root / "photos"
            imgs.mkdir()
            for i in range(3):
                (imgs / f"p{i}.jpg").write_bytes(bytes([i]))
            ws = AnnotationWorkspace(imgs, root / "work")
            ws.save(ws.photos[0], "vehicle",
                    "2 0.1 0.1 0.9 0.1 0.9 0.9\n")
            ws.save(ws.photos[1], "vehicle", "")
            ws.save(ws.photos[0], "obstacle", "0 0.5 0.5 0.2 0.2\n")
            poly = layout_polygon_to_yolo(1, [(1, 1), (50, 1), (50, 20)], 100, 100)
            ws.save(ws.photos[2], "layout", poly + "\n")
            data = build_report(ws)
            self.assertEqual(data["images"], 3)
            self.assertEqual(data["tasks"]["vehicle"]["reviewed"], 2)
            self.assertEqual(data["tasks"]["vehicle"]["negatives"], 1)
            self.assertEqual(data["tasks"]["vehicle"]["unreviewed"], 1)
            self.assertEqual(data["tasks"]["obstacle"]["objects_total"], 1)
            self.assertEqual(data["tasks"]["layout"]["classes"]["1"]["count"], 1)
            self.assertEqual(data["tasks"]["layout"]["unreviewed"], 2)


if __name__ == "__main__":
    unittest.main()
