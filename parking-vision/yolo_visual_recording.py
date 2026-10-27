#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YOLOの検出枠・追跡ID・区画状態を描画した映像を、元映像とは別に記録。

カメラの生映像はcamera_recording.RecordingCameraが連続録画する。
こちらは「YOLOが実際に解析したフレーム」のみ受け取り、次の判定結果まで
その画面を保持する。固定FPSの動画でも時間が縮まないよう、経過時間で補う。
補ったコマは新たに解析したフレームではない（画面内の判定時刻は変わらない）。
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
import time


class YoloVisualRecorder:
    """研究用の判定付き動画。保存先は生映像と同じPC内の実験フォルダ。"""

    def __init__(self, folder, cv2, session_start, fps=5, segment_seconds=600):
        self.folder = Path(folder)
        self.cv2 = cv2
        self.session_start = float(session_start)
        self.fps = int(fps)
        self.segment_seconds = int(segment_seconds)
        if not 1 <= self.fps <= 15:
            raise ValueError("yolo_recording_fps は1～15の整数にしてください")
        if not 60 <= self.segment_seconds <= 3600:
            raise ValueError("recording_segment_seconds は60～3600の整数にしてください")
        self._writer = None
        self._previous = None
        self._next_write = 0.
        self._segment_started = 0.
        self._last_result_at = None
        self._number = 0
        self._manifest = (self.folder / "YOLO判定ファイル一覧.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        self._csv = csv.writer(self._manifest)
        self._csv.writerow(["動画ファイル", "録画開始からの秒数", "判定動画の開始日時"])
        self._manifest.flush()

    def _open(self, frame, now):
        """MP4が使えなければAVI。動画の書込み可否は必ずチェックする。"""
        h, w = frame.shape[:2]
        if h <= 0 or w <= 0:
            raise RuntimeError("YOLO判定映像のサイズが不正です")
        self._number += 1
        filename = f"YOLO判定_{self._number:03d}.mp4"
        path = self.folder / filename
        writer = self.cv2.VideoWriter(
            str(path), self.cv2.VideoWriter_fourcc(*"mp4v"),
            self.fps, (w, h)
        )
        if not writer.isOpened():
            writer.release()
            path.unlink(missing_ok=True)
            filename = f"YOLO判定_{self._number:03d}.avi"
            path = self.folder / filename
            writer = self.cv2.VideoWriter(
                str(path), self.cv2.VideoWriter_fourcc(*"XVID"),
                self.fps, (w, h)
            )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("YOLO判定付き動画を保存できません。ディスク容量とコーデックを確認してください")
        self._writer = writer
        self._segment_started = now
        self._next_write = now
        self._previous = None
        self._csv.writerow([
            filename, f"{now - self.session_start:.3f}",
            datetime.now().astimezone().isoformat(timespec="seconds"),
        ])
        self._manifest.flush()
        print(f"【YOLO判定を録画中】{path}", flush=True)

    def write(self, annotated_frame, now=None):
        """一回の推論結果を記録。AIが未実行だった時間を新規判定と偽らない。"""
        if self._manifest.closed:
            raise RuntimeError("終了済みのYOLO判定録画には追記できません")
        if now is None:
            now = time.monotonic()
        if self._writer is None or now - self._segment_started >= self.segment_seconds:
            self._close_video()
            self._open(annotated_frame, now)
        elif self._last_result_at is not None and now - self._last_result_at > 5:
            # AIが5秒超停止した区間を、正常に判定が連続した映像と誤認させない。
            print("【YOLO録画】判定間隔が5秒を超えたため、動画を分割しました。", flush=True)
            self._close_video()
            self._open(annotated_frame, now)

        self._last_result_at = now
        if now < self._next_write:
            self._previous = annotated_frame.copy()
            return

        count = int((now - self._next_write) * self.fps + 1e-6) + 1
        # 最初に現在の結果を記録。後続は前の解析結果を画面に保持する。
        for index in range(count):
            frame = (self._previous
                     if index < count - 1 and self._previous is not None
                     else annotated_frame)
            self._writer.write(frame)
        self._next_write += count / self.fps
        self._previous = annotated_frame.copy()

    def _close_video(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def close(self):
        """MP4のインデックスを確定し、Windowsで再生できるようにする。"""
        try:
            self._close_video()
        finally:
            if not self._manifest.closed:
                self._manifest.close()
