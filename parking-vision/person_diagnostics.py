# -*- coding: utf-8 -*-
"""研究用の人物追跡診断CSV。顔画像・個人情報は保存しません。"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


class PersonDiagnosticRecorder:
    COLUMNS = (
        "判定日時", "動画経過秒", "YOLO人物生ID", "画面用安定人物ID",
        "ID表示確定", "検出信頼度", "人物検出枠", "車と重なっている",
    )

    def __init__(self, folder):
        self.path = Path(folder) / "人物追跡_判定診断.csv"
        self.file = self.path.open("w", encoding="utf-8-sig", newline="")
        self.csv = csv.writer(self.file)
        self.csv.writerow(self.COLUMNS)

    def write(self, blockers, elapsed):
        stamped = datetime.now().astimezone().isoformat(timespec="seconds")
        for det in blockers:
            if det.get("name") != "person":
                continue
            bbox = det.get("bbox") or []
            self.csv.writerow([
                stamped, round(float(elapsed), 2),
                det.get("raw_person_track_id")
                if det.get("raw_person_track_id") is not None else "",
                det.get("track_id")
                if det.get("person_confirmed") else "",
                "yes" if det.get("person_confirmed") else "no",
                round(float(det.get("confidence", 0)), 3),
                ",".join(str(int(x)) for x in bbox),
                "yes" if det.get("near_vehicle") else "no",
            ])
        self.file.flush()

    def close(self):
        self.file.close()
