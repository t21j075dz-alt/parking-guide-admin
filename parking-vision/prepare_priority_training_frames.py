# -*- coding: utf-8 -*-
"""Extract candidate frames from ORIGINAL parking videos for human annotation.

Compatible with vehicle_mask_dataset.py's annotation_manifest.csv.
No automatic labels, training, live model changes, cloud uploads, or user-app writes.
Separate source recording sessions MUST be used for train, val and test.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from vehicle_mask_dataset import sha256_file

FOCUS_PATTERN = re.compile(
    r"(?P<start>[0-9]+(?:\.[0-9]+)?)-(?P<end>[0-9]+(?:\.[0-9]+)?):"
    r"(?P<tag>[a-z][a-z0-9_-]{0,31})\Z"
)


def parse_focus_ranges(specs, duration):
    """Read repeated '154-169:turning' windows (seconds, not frame numbers)."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("動画の長さが不正です")
    windows = []
    for spec in specs:
        match = FOCUS_PATTERN.fullmatch(spec.strip())
        if not match:
            raise ValueError(
                f"重点区間の書式が不正です: {spec} (例: 154-169:turning)")
        start = float(match["start"])
        end = float(match["end"])
        if (not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start or start >= duration):
            raise ValueError(f"重点区間が動画内に収まりません: {spec}")
        windows.append((start, min(end, duration), match["tag"]))
    return windows


def select_timestamps(duration, *, interval, focus_step, windows):
    """Return [(timestamp, tags)] without artificially labeled positives."""
    if not all(math.isfinite(v) and v > 0 for v in
               (duration, interval, focus_step)):
        raise ValueError("動画の長さ・抽出間隔は正の有限値にしてください")
    seconds = set()
    sec = 0.0
    while sec < duration:
        seconds.add(round(sec, 3))
        sec += interval
    for start, end, _ in windows:
        sec = start
        while sec < end:
            seconds.add(round(sec, 3))
            sec += focus_step
    result = []
    for sec in sorted(t for t in seconds if 0 <= t < duration):
        tags = sorted({tag for start, end, tag in windows
                       if start <= sec < end})
        result.append((sec, tags))
    return result


def extract(video, output, *, task, interval, focus_step, focus_specs):
    """Keep each export tied to a single original recording's SHA256."""
    import cv2

    video = Path(video).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not video.is_file():
        raise ValueError(f"元動画がありません: {video}")
    name = video.name.lower()
    if "yolo判定" in name or "yolo_annotated" in name or "判定済" in name:
        raise ValueError("YOLOの判定枠を焼き込んだ動画は教師データに使用できません")
    if output.exists() and any(output.iterdir()):
        raise ValueError("既存ファイルのある出力先は上書きしません")
    if output == video.parent:
        raise ValueError("元動画の保存フォルダを出力先にしないでください")

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError(f"動画を開けません: {video}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        total_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if (not math.isfinite(fps) or not math.isfinite(total_frames)
                or fps <= 0 or total_frames <= 0):
            raise ValueError("動画のFPS・総フレーム数が不明です")
        duration = total_frames / fps
        windows = parse_focus_ranges(focus_specs, duration)
        timestamps = select_timestamps(duration, interval=interval,
                                       focus_step=focus_step, windows=windows)
        source_hash = sha256_file(video)
        output.mkdir(parents=True, exist_ok=True)
        saved = []
        used_frames = set()
        for timestamp, tags in timestamps:
            frame_index = min(int(round(timestamp * fps)), int(total_frames) - 1)
            if frame_index in used_frames:
                continue
            used_frames.add(frame_index)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            filename = f"frame_{frame_index:08d}_{timestamp:08.2f}s.jpg"
            encoded_ok, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if not encoded_ok:
                continue
            (output / filename).write_bytes(buffer.tobytes())
            saved.append([f"{timestamp:.3f}", frame_index, filename,
                          source_hash, "|".join(tags), task])
        if not saved:
            raise ValueError("画像を抽出できませんでした。動画を確認してください")
        with (output / "annotation_manifest.csv").open(
                "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["video_seconds", "frame_index", "image",
                             "source_video_sha256", "scene_tags", "task"])
            writer.writerows(saved)
        (output / "collection_summary.json").write_text(
            json.dumps({"task": task, "source_video_sha256": source_hash,
                        "duration_seconds": round(duration, 3),
                        "exported_frames": len(saved),
                        "focus_windows": [{"start": start, "end": end, "tag": tag}
                                          for start, end, tag in windows],
                        "annotation_status": "unlabeled",
                        "warning": "All labels must be reviewed by a human. "
                                   "Use independent original videos for "
                                   "train/val/test. Do not upload raw footage."},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return len(saved), output
    finally:
        capture.release()


def main():
    parser = argparse.ArgumentParser(
        description="誤判定場面を重点抽出し、YOLO追加学習用の未ラベル画像を準備")
    parser.add_argument("--video", required=True, help="認識枠を描き込んでいない元動画")
    parser.add_argument("--output", required=True,
                        help="空の新規フォルダ（例: vehicle_mask_sessions/session_A）")
    parser.add_argument("--task", choices=["segment", "obstacles"],
                        default="segment", help="輪郭か障害物か。ラベル形式は混在禁止")
    parser.add_argument("--interval", type=float, default=30.,
                        help="動画全体の通常抽出間隔（秒）")
    parser.add_argument("--focus-step", type=float, default=2.,
                        help="重点区間の抽出間隔（秒）")
    parser.add_argument("--focus", action="append", default=[],
                        help="複数指定可。例: --focus 154-169:turning")
    args = parser.parse_args()
    try:
        count, destination = extract(
            args.video, args.output, task=args.task, interval=args.interval,
            focus_step=args.focus_step, focus_specs=args.focus)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"未ラベル画像を{count}枚抽出しました: {destination}")
    print("これは学習完了ではありません。画像ごとに正解ラベルを付けてください。")
    print("個人情報を含み得る元動画・画像・ラベルはPC内で管理してください。")


if __name__ == "__main__":
    main()
