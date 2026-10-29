"""Human ID display regression: no false identity explosion, no car mix."""
import unittest

from person_stability import PersonIdStabilizer
from person_diagnostics import PersonDiagnosticRecorder
from pathlib import Path
import csv
import tempfile


def human(raw, x, y=.45, conf=.9):
    return {
        "name": "person", "track_id": raw, "confidence": conf,
        "point": (x, y), "bbox": [int(x*1000)-12, int(y*1000)-45,
                                  int(x*1000)+12, int(y*1000)+45],
    }


class HumanIdTests(unittest.TestCase):
    def test_single_frame_false_positive_never_gets_public_id(self):
        ids = PersonIdStabilizer()
        x = human(12,.4)
        ids.update([x],0)
        self.assertIsNone(x["track_id"])
        self.assertFalse(x["person_confirmed"])

    def test_same_person_new_raw_yolo_id_keeps_public_id(self):
        ids = PersonIdStabilizer()
        for time, raw, x in [(0,12,.400),(.6,12,.405),(1.2,57,.410)]:
            item=human(raw,x)
            ids.update([item],time)
        self.assertEqual(item["track_id"],1)
        self.assertTrue(item["person_confirmed"])
        new=human(92,.417)
        ids.update([new],1.8)
        self.assertEqual(new["track_id"],1)

    def test_two_people_simultaneous_never_share_public_id(self):
        ids = PersonIdStabilizer()
        for clock in (0,.6,1.2,1.8):
            people=[human(1+int(clock),.2),human(10+int(clock),.8)]
            ids.update(people,clock)
        self.assertEqual([p["track_id"] for p in people],[1,2])

    def test_low_confidence_cannot_create_identity(self):
        ids=PersonIdStabilizer()
        for clock in (0,.8,1.6,2.4):
            item=human(clock,.4,conf=.25)
            ids.update([item],clock)
            self.assertIsNone(item["track_id"])
        self.assertEqual(ids.tracks,{})

    def test_person_diagnostic_writes_raw_and_stable_ids_without_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            recorder=PersonDiagnosticRecorder(path)
            ids=PersonIdStabilizer()
            for t, raw in [(0,1),(.5,11),(1.1,19)]:
                person=human(raw,.40)
                ids.update([person],t)
                recorder.write([person],t)
            recorder.close()
            with (path/"人物追跡_判定診断.csv").open(
                encoding="utf-8-sig",newline=""
            ) as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),3)
            self.assertEqual([r["YOLO人物生ID"] for r in rows],
                             ["1","11","19"])
            self.assertEqual(rows[-1]["画面用安定人物ID"],"1")
            self.assertEqual(rows[0]["画面用安定人物ID"],"")
            self.assertEqual(rows[-1]["ID表示確定"],"yes")

    def test_nonhuman_ids_are_not_exposed(self):
        ids=PersonIdStabilizer()
        blocker={"name":"cone","track_id":33,"confidence":.99}
        ids.update([blocker],0)
        self.assertIsNone(blocker["track_id"])

if __name__=="__main__":
    unittest.main()
