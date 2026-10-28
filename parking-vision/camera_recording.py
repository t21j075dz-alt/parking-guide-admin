#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""実カメラの取得・ローカル録画を担当する。YOLOの処理と録画を分離する。

- カメラを読むのはこのスレッドだけ。YOLOは最新画像のコピーを読む。
- 録画はPC内のLOCALAPPDATAに保存し、SupabaseやGitHubには送らない。
- 固定FPSの動画と実時間の差を小さくするため、遅れた部分は直近画像で補う。
  ただしカメラから取得できなかった瞬間の映像は復元できない。
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import threading
import time
from uuid import uuid4


def open_camera(cv2, source, backend="auto", manual_exposure=None,
                capture_width=0, capture_height=0, capture_fps=0):
    """映像取得・録画・判定で同じカメラと露出設定を使う。"""
    from camera_exposure import is_valid_manual_exposure, set_manual_exposure

    if isinstance(source, str) and source.isdecimal():
        source = int(source)
    if isinstance(source, int):
        if source < 0:
            raise ValueError("外付けWebカメラが未選択です。かんたん準備を実行してください。")
        names = {"dshow": "CAP_DSHOW", "msmf": "CAP_MSMF"}
        if os.name == "nt" and backend in names:
            camera = cv2.VideoCapture(source, getattr(cv2, names[backend]))
        else:
            camera = cv2.VideoCapture(source)
    else:
        camera = cv2.VideoCapture(source)

    # 解像度が未指定ならカメラ標準のフレーム全体を使う。
    # 指定時も切り抜きは行わず、ドライバーに解像度変更を要求するのみ。
    if camera.isOpened() and isinstance(source, int):
        width, height, fps = (int(capture_width or 0), int(capture_height or 0),
                              int(capture_fps or 0))
        if width > 0 and height > 0:
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if fps > 0:
            camera.set(cv2.CAP_PROP_FPS, fps)
        print("【カメラ接続】要求解像度: " +
              (f"{width}x{height}" if width and height else "標準（切り抜きなし）"), flush=True)
        print("【カメラ接続】実際の出力: " +
              f"{camera.get(cv2.CAP_PROP_FRAME_WIDTH):.0f}x"
              f"{camera.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f}", flush=True)
        print("【注意】Camo側のデジタルズーム/クロップはiPhoneまたはCamo Studio側で解除してください。", flush=True)

    # カメラを開き直すと露出がリセットされる機種のため、毎回反映する。
    if camera.isOpened() and is_valid_manual_exposure(manual_exposure):
        if not set_manual_exposure(camera, cv2, manual_exposure):
            print("【露出】保存済みの設定をカメラに適用できません。"
                  "カメラの設定画面で自動露出をOFFにしてください。", flush=True)
    return camera


def default_recording_root() -> Path:
    """OneDrive等の同期フォルダを避け、Windowsのローカル保存先を使う。"""
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) if local else Path.home() / ".local" / "share") / "ParkingResearch" / "Recordings"


class RecordingCamera:
    """連続録画しながら最新のカメラ画像をYOLOへ渡す。

    出力:
      映像_001.mp4（環境でMP4が使えない場合はAVI）
      録画ファイル一覧.csv  /  区画状態の変化.csv
    """

    def __init__(self, camera, cv2, root=None, fps=10, segment_seconds=600,
                 min_free_bytes=1024 ** 3):
        self.camera = camera
        self.cv2 = cv2
        self.fps = int(fps)
        self.segment_seconds = int(segment_seconds)
        self.min_free_bytes = int(min_free_bytes)
        if not 1 <= self.fps <= 30:
            raise ValueError("recording_fps は1～30で指定してください")
        if not 60 <= self.segment_seconds <= 3600:
            raise ValueError("recording_segment_seconds は60～3600で指定してください")

        self.root = Path(root) if root is not None else default_recording_root()
        self.folder = None
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._latest = None
        self._sequence = 0
        self._finished = False
        self._error = None
        self._writer = None
        self._segment_number = 0
        self._segment_started = 0.0
        self._next_write = 0.0
        self._started = 0.0
        self._wall_start = None  # 実時間と動画内時刻を同じ起点にそろえる。
        self._last_written_frame = None
        self._last_disk_check = 0.0
        self._file_index = None
        self._status_file = None
        self._status_writer = None

    def start(self):
        """録画ファイルが実際に開けるまで待つ。失敗時は判定を開始しない。"""
        if self._thread is not None:
            raise RuntimeError("この録画処理はすでに開始されています")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.folder = self.root / stamp[:8] / (stamp + "_" + uuid4().hex[:6])
        self.folder.mkdir(parents=True, exist_ok=False)
        self._file_index = (self.folder / "録画ファイル一覧.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        self._index_writer = csv.writer(self._file_index)
        self._index_writer.writerow(["動画ファイル", "録画開始からの秒数", "動画の開始日時"])
        self._file_index.flush()
        self._status_file = (self.folder / "区画状態の変化.csv").open(
            "w", newline="", encoding="utf-8-sig"
        )
        self._status_writer = csv.writer(self._status_file)
        self._status_writer.writerow(["判定日時", "録画開始からの秒数", "区画UID", "判定状態"])
        self._status_file.flush()

        self._started = time.monotonic()
        self._wall_start = datetime.now().astimezone()
        self._thread = threading.Thread(target=self._worker, name="parking-camera-recording",
                                        daemon=True)
        self._thread.start()
        with self._condition:
            ready = self._condition.wait_for(
                lambda: self._sequence > 0 or self._finished, timeout=12
            )
        if not ready or self._sequence == 0:
            reason = self._error or "カメラの映像・録画の開始を確認できませんでした"
            self.close()
            raise RuntimeError(reason)
        return self.folder

    def _check_storage(self, now):
        # 定期的に空き容量を確認。自動削除はしない。
        if self._last_disk_check and now - self._last_disk_check < 30:
            return
        self._last_disk_check = now
        if shutil.disk_usage(self.folder).free < self.min_free_bytes:
            raise RuntimeError(
                "録画用ディスクの空き容量が不足しました。録画・ライブ判定を停止します。"
            )

    def _open_video(self, frame, now):
        self._check_storage(now)
        height, width = frame.shape[:2]
        if width < 1 or height < 1:
            raise RuntimeError("カメラ画像の大きさが不正です")
        self._segment_number += 1
        filename = f"映像_{self._segment_number:03d}.mp4"
        path = self.folder / filename
        fourcc = self.cv2.VideoWriter_fourcc(*"mp4v")
        writer = self.cv2.VideoWriter(str(path), fourcc, self.fps, (width, height))
        if not writer.isOpened():
            writer.release()
            path.unlink(missing_ok=True)
            filename = f"映像_{self._segment_number:03d}.avi"
            path = self.folder / filename
            writer = self.cv2.VideoWriter(
                str(path), self.cv2.VideoWriter_fourcc(*"XVID"),
                self.fps, (width, height)
            )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("動画を保存できません。空き容量とOpenCVの動画コーデックを確認してください")
        self._writer = writer
        self._segment_started = now
        self._next_write = now
        self._last_written_frame = None
        self._index_writer.writerow([
            filename, f"{now - self._started:.3f}",
            datetime.now().astimezone().isoformat(timespec="seconds")
        ])
        self._file_index.flush()
        print(f"【録画中】{path}", flush=True)

    def _record(self, frame, now):
        """実時間の固定間隔で動画を保存し、CVSの経過秒数と再生位置を合わせる。

        たとえばカメラ実測8fps・録画設定10fpsなら、足りない2コマ分は
        直前画像で補う。毎回のread後に次回時刻をnowへリセットしない。
        5秒を超える取得停止は画像を捏造せず、新しい動画として記録する。
        """
        self._check_storage(now)
        if self._writer is None or now - self._segment_started >= self.segment_seconds:
            self._close_video()
            self._open_video(frame, now)

        # 録画FPSを基準とする絶対時刻。readが遅い機種でも時間は縮めない。
        if now < self._next_write:
            self._last_written_frame = frame.copy()
            return
        due = int((now - self._next_write) * self.fps + 1e-6) + 1
        if due > self.fps * 5:
            # 5秒超の大きな穴は、連続録画だったと偽らない。
            print("【注意】カメラの映像取得が5秒以上途切れました。"
                  "録画を新しいファイルに分けます。", flush=True)
            self._close_video()
            self._open_video(frame, now)
            due = 1

        for index in range(due):
            # 欠落区間には、最後に実際に取得できた画像を使う。
            # 最後の1コマだけ現在の最新画像に切り替える。
            source = (
                self._last_written_frame
                if index < due - 1 and self._last_written_frame is not None
                else frame
            )
            view = source.copy()
            frame_time = self._next_write + index / self.fps
            shown_at = self._wall_start + timedelta(seconds=frame_time - self._started)
            timestamp = shown_at.strftime("%Y-%m-%d %H:%M:%S")
            self.cv2.putText(
                view, "REC " + timestamp, (12, 28),
                self.cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2
            )
            self._writer.write(view)

        self._next_write += due / self.fps
        self._last_written_frame = frame.copy()

    def _close_video(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def _worker(self):
        try:
            while not self._stop.is_set():
                ok, frame = self.camera.read()
                if not ok or frame is None:
                    raise RuntimeError("外付けカメラの映像が途切れました。録画・ライブ判定を停止します")
                # カメラが動作中に解像度/画角を切り替えた場合は停止。
                # 古い区画座標と違う映像を「空き」として送らない。
                dimensions = frame.shape[:2]
                if not hasattr(self, "_frame_dimensions"):
                    self._frame_dimensions = dimensions
                elif dimensions != self._frame_dimensions:
                    raise RuntimeError("撮影中に映像サイズが変わりました。"
                                       "区画設定の確認後に再起動してください")
                now = time.monotonic()
                self._record(frame, now)
                with self._condition:
                    self._latest = frame.copy()
                    self._sequence += 1
                    self._condition.notify_all()
        except Exception as exc:
            self._error = str(exc)
        finally:
            self._close_video()
            with self._condition:
                self._finished = True
                self._condition.notify_all()

    def next_frame(self, previous_number=0, timeout=8):
        """前回と異なる最新画像を返す。カメラ断や録画失敗を無視しない。"""
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > previous_number or self._finished, timeout=timeout
            )
            if self._error:
                raise RuntimeError(self._error)
            if self._sequence <= previous_number:
                raise RuntimeError("カメラから新しい映像を取得できませんでした")
            return self._latest.copy(), self._sequence

    def log_status(self, statuses):
        """YOLO判定が変わった時刻を、再生用の動画と照合できるCSVに記録。"""
        if self._status_writer is None:
            return
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        elapsed = f"{time.monotonic() - self._started:.3f}"
        for uid, status in statuses.items():
            self._status_writer.writerow([timestamp, elapsed, uid, status])
        self._status_file.flush()

    def close(self):
        """停止時に動画・CSVを確定。古い録画は消さない。"""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=4)
            if self._thread.is_alive():
                # 一部USBドライバのread()が止まらない場合、デバイス解放で解除を試す。
                self.camera.release()
                self._thread.join(timeout=4)
            if self._thread.is_alive():
                print("【注意】カメラが応答せず、録画終了の確認ができません", flush=True)
        if self._file_index is not None:
            self._file_index.close()
            self._file_index = None
        if self._status_file is not None:
            self._status_file.close()
            self._status_file = None
