"""過去の日光動画の静止画を明示許可時だけ研究用画面へ共有する。

実ライブと混同させないよう映像に常時ウォーターマークを入れ、5秒ごとに
最新の縮小画像1枚だけを更新する。動画原本・音声は送信しない。
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import time
from urllib import parse, request


class RecordedSnapshotPublisher:
    """Nikko-specific opt-in stills; never used with physical cameras."""

    def __init__(self, writer, config, interval_seconds=5.0):
        if not writer or config.get("facility_id") != "nikko-test-001" or (
                config.get("camera_id") != "nikko-recording-01"
                or config.get("video_demo_only") is not True):
            raise ValueError("日光の録画専用カメラだけ画像共有できます")
        if interval_seconds < 3:
            raise ValueError("画像の更新間隔は3秒以上にしてください")
        self.writer, self.config = writer, config
        self.interval_seconds = interval_seconds
        self.last_at = float("-inf")

    def publish(self, frame, elapsed=0.0, cycle=1, now=None):
        import cv2

        now = time.monotonic() if now is None else now
        if now - self.last_at < self.interval_seconds:
            return False
        # 失敗時も無制限リトライ・画像の蓄積を避ける。
        self.last_at = now
        height, width = frame.shape[:2]
        if height < 1 or width < 1:
            raise ValueError("画像サイズが不正です")
        target_width = min(960, width)
        scaled = cv2.resize(frame, (target_width, max(1, round(height*target_width/width))),
                            interpolation=cv2.INTER_AREA) if target_width < width else frame.copy()
        output_height, output_width = scaled.shape[:2]
        cv2.rectangle(scaled, (0, 0), (output_width, 58), (12, 18, 96), -1)
        cv2.putText(scaled, "RECORDED VIDEO / NOT LIVE", (12, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(scaled, f"LOOP {cycle} / {elapsed:.1f} sec", (12, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1, cv2.LINE_AA)
        ok, jpeg = cv2.imencode(".jpg", scaled, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if not ok or jpeg.nbytes > 1_500_000:
            raise ValueError("録画写真の圧縮に失敗しました")
        row = {
            "facility_id": "nikko-test-001",
            "camera_id": "nikko-recording-01",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "image_data": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
        }
        self.writer.upsert("parking_camera_private", [row], "facility_id,camera_id")
        self.writer.upsert("parking_camera_public", [{**row, "is_published": True}],
                           "facility_id,camera_id")
        return True

    def disable_public(self):
        """終了解除時も録画写真を現在のカメラ画像として公開しない。"""
        self.writer._ensure_token()
        url = (f"{self.writer.url}/rest/v1/parking_camera_public?"
               "facility_id=eq.nikko-test-001&camera_id=eq.nikko-recording-01")
        req = request.Request(url, data=json.dumps({"is_published": False}).encode("utf-8"),
                              method="PATCH", headers={
            "apikey": self.writer.key,
            "Authorization": f"Bearer {self.writer.access_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        })
        with request.urlopen(req, timeout=10) as response:
            rows = json.loads(response.read() or b"[]")
        if len(rows) > 1 or (rows and (rows[0].get("facility_id") != "nikko-test-001"
                                      or rows[0].get("camera_id") != "nikko-recording-01")):
            raise ValueError("録画写真の公開解除結果が不正です")
        return len(rows)
