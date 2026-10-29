# -*- coding: utf-8 -*-
"""Local-only parking-zone diagnosis; no images, passwords or location saved."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path


class ParkingDiagnosticRecorder:
    """One snapshot per interval, Excel-readable UTF-8 BOM CSV.

    Saved next to raw and annotated recordings on the local computer, never
    published to Supabase. Records why YOLO and parking-status disagree.
    """
    FIELDS = (
        "日時", "追跡ID", "車両状態", "停止判定", "検出信頼度",
        "瞬間区画", "安定区画", "区画票数", "判定根拠",
        "車両検出枠", "区画状態の一覧", "注意事項",
    )

    def __init__(self, folder, interval_seconds=2.0):
        self.path = Path(folder) / "駐車区画_判定診断.csv"
        self.file = self.path.open("w", encoding="utf-8-sig", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(self.FIELDS)
        self.interval = max(0.5, float(interval_seconds))
        self.last = None

    def write(self, vehicles, zones, statuses, now):
        if self.last is not None and now - self.last < self.interval:
            return
        self.last = float(now)
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        state_summary = " / ".join(
            f"{uid}={statuses.get(uid, 'unknown')}" for uid in zones)
        if not vehicles:
            self.writer.writerow([
                stamp, "", "not detected", "", "", "", "", 0, "",
                "", state_summary, "NO_CAR",
            ])
        for vehicle in vehicles:
            instantaneous = vehicle.get("zone_candidate") or ""
            stable = vehicle.get("zone_smoothed") or ""
            phase = vehicle.get("phase") or ""
            basis = vehicle.get("zone_basis") or "unknown"
            warnings = []
            if not instantaneous:
                warnings.append("ZONE_UNKNOWN")
            if basis == "conflict":
                warnings.append("WHEEL_BODY_CONFLICT")
            if not vehicle.get("stationary"):
                warnings.append("NOT_STATIONARY")
            if not stable:
                warnings.append("NOT_ENOUGH_ZONE_VOTES")
            self.writer.writerow([
                stamp, vehicle.get("track_id") if vehicle.get("track_id") is not None else "",
                phase, int(bool(vehicle.get("stationary"))),
                round(float(vehicle.get("confidence", 0)), 3),
                instantaneous, stable, vehicle.get("zone_votes", 0), basis,
                ",".join(str(int(v)) for v in vehicle.get("bbox", [])),
                state_summary, "|".join(warnings),
            ])
        self.file.flush()

    def close(self):
        if not self.file.closed:
            self.file.close()
