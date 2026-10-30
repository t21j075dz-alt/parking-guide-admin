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
    if path.name.startswith("YOLO判定_") or path.name.lower().startswith("yolo_annotated"):
        raise ValueError(
            "これはYOLOの判定結果を重ねた動画です。"
            "再解析には元の『映像_001.mp4』など、1280x720の元録画を選んでください"
        )
    if path.stat().st_size == 0:
        raise ValueError("録画ファイルが空です")
    return path


class VideoReplay:
    """monitor.pyの録画入力インターフェースを実装。クラウド機能は持たない。"""

    def __init__(self, filename, cv2, root=None, clock=time.monotonic, sleeper=time.sleep, loop=False):
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
        self.loop_enabled = bool(loop)
        self.cycle_number = 0  # 0=1周目、1=2周目。メイン側の追跡初期化に利用。
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
        self._status_writer.writerow(["判定日時", "録画経過秒数", "区画UID", "判定状態", "車両段階", "周回"])
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

    def _restart_video(self):
        """動画の先頭へ戻る。周回をまたぐ追跡情報は呼び出し元で初期化する。"""
        if not self.capture.set(self.cv2.CAP_PROP_POS_FRAMES, 0):
            self.capture.release()
            self.capture = self.cv2.VideoCapture(str(self.filename))
            if not self.capture.isOpened():
                raise ValueError("録画を先頭から開き直せませんでした。")
        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise ValueError("ループ再生の最初のフレームを読み取れません。")
        self.frame_index = 0
        self.cycle_number += 1
        self._started = self.clock()
        self._last_skipped = 0
        self._first = frame.copy()
        print(f"【録画ループ】{self.cycle_number + 1}周目を開始。"
              "車両追跡と駐車状態は先頭から再判定します。")
        return frame, 1

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
            if self.loop_enabled:
                return self._restart_video()
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
            if self.loop_enabled:
                return self._restart_video()
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
            self._status_writer.writerow([timestamp, elapsed, uid, status, (phases or {}).get(uid, "unknown"), self.cycle_number + 1])
        self._status_file.flush()

    def close(self):
        self.capture.release()
        if self._status_file is not None:
            self._status_file.close()
            self._status_file = None
