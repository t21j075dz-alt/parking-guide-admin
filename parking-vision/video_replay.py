#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実時間に合わせて録画映像をYOLOへ渡す仮想カメラ。

Webカメラと違い録画は既に存在するので、元映像を再録画しない。
YOLOが間に合わないコマはスキップし、動画時刻と実時間のずれを防ぐ。
映像の再生位置を早送りしても、駐車の検知結果を捏造しない。
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import time
from uuid import uuid4

from camera_recording import default_recording_root


SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def validate_video(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"録画ファイルが見つかりません: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("動画はMP4/AVI/MOV/MKV/WebMを選択してください")
    if path.stat().st_size == 0:
        raise ValueError("録画ファイルが空です")
    return path


class VideoReplay:
    """monitor.pyの録画入力インターフェースを実装。クラウド機能は持たない。"""

    def __init__(self, filename, cv2, root=None, clock=time.monotonic, sleeper=time.sleep):
        self.filename = validate_video(filename)
        self.cv2 = cv2
        self.clock, self.sleeper = clock, sleeper
        self.capture = cv2.VideoCapture(str(self.filename))
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError("録画動画を開けません。形式またはコーデックを確認してください")
        self.fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        if not 1 <= self.fps <= 120:
            self.capture.release()
            raise ValueError("動画のFPSを取得できません。FPS付きの動画を用意してください")
        self.frame_total = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_index = -1
        self._started = None
        self._first = None
        self._status_file = None
        self._status_writer = None
        self._last_skipped = 0
        self.folder = None
        self.root = Path(root) if root is not None else default_recording_root()

    def start(self):
        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise ValueError("録画の最初のフレームが読み取れません")
        self.frame_index = 0
        self._first = frame.copy()
        self._started = self.clock()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.folder = self.root / stamp[:8] / (stamp + "_VIDEO_DEMO_" + uuid4().hex[:6])
        self.folder.mkdir(parents=True, exist_ok=False)
        self._status_file = (self.folder / "区画状態の変化.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        self._status_writer = csv.writer(self._status_file)
        self._status_writer.writerow(["判定日時", "録画経過秒数", "区画UID", "判定状態", "車両段階"])
        self._status_file.flush()
        print(f"【録画実演】{self.filename.name} / FPS {self.fps:.2f} / "
              f"総フレーム {self.frame_total or '不明'}")
        print("【原本】動画ファイルは上書きせず、解析結果だけ別フォルダに残します。")
        return self.folder

    def reset_clock_after_confirmation(self):
        """Start playback only after the operator checks the zone overlay."""
        if self._first is None or self.frame_index != 0:
            raise RuntimeError("再生を開始する前にだけ時刻をリセットできます")
        self._started = self.clock()

    def next_frame(self, previous_number=0, timeout=None):
        if self._started is None:
            raise RuntimeError("先にstart()を呼び出してください")
        if previous_number == 0:
            return self._first.copy(), 1
        # Exactly one real decoded frame per new observation. CPU/GPU processing
        # overruns cannot slow the virtual playback clock indefinitely.
        target = max(self.frame_index + 1,
                     int((self.clock() - self._started) * self.fps))
        if self.frame_total > 0 and target >= self.frame_total:
            print("【録画実演終了】録画の最後まで再生しました。")
            return None, previous_number
        skipped = target - (self.frame_index + 1)
        if skipped > 0:
            if not self.capture.set(self.cv2.CAP_PROP_POS_FRAMES, target):
                # Fall back to sequential GRAB; never reuse a stale frame.
                for _ in range(skipped):
                    if not self.capture.grab():
                        return None, previous_number
            if skipped - self._last_skipped >= 10 or self._last_skipped == 0:
                print(f"【解析速度】YOLO処理が動画FPSに追い付かず、"
                      f"{skipped}コマを飛ばしました。")
            self._last_skipped = skipped
        due_at = self._started + target / self.fps
        delay = due_at - self.clock()
        if delay > 0:
            self.sleeper(delay)
        ok, frame = self.capture.read()
        if not ok or frame is None:
            print("【録画実演終了】動画の末尾まで読み込みました。")
            return None, previous_number
        self.frame_index = target
        return frame, target + 1

    def log_status(self, statuses, phases=None):
        if self._status_writer is None:
            return
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        elapsed = f"{self.frame_index / self.fps:.3f}"
        for uid, status in statuses.items():
            self._status_writer.writerow([timestamp, elapsed, uid, status, (phases or {}).get(uid, "unknown")])
        self._status_file.flush()

    def close(self):
        self.capture.release()
        if self._status_file is not None:
            self._status_file.close()
            self._status_file = None
