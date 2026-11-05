# -*- coding: utf-8 -*-
"""Export clean original-video frames for MANUAL vehicle mask annotation.

Does not learn, label, or change a YOLO model automatically. The default
sampling emphasizes the user's documented 150–190s turning/re-parking scene,
plus regular frames elsewhere to reduce training-set angle bias.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from vehicle_mask_dataset import sha256_file


def sampling_seconds(duration, interval=30., focus_start=148.,
                     focus_end=190., focus_step=2.):
    """Generate unique, ascending timestamps within the ORIGINAL video."""
    if duration <= 0 or interval <= 0 or focus_step <= 0:
        raise ValueError("動画の長さと抽出間隔は正の値にしてください")
    seconds = set()
    value = 0.
    while value < duration:
        seconds.add(round(value, 3))
        value += interval
    value = max(0., focus_start)
    while value <= min(focus_end, duration - .001):
        seconds.add(round(value, 3))
        value += focus_step
    return sorted(t for t in seconds if 0 <= t < duration)


def main():
    parser = argparse.ArgumentParser(
        description="元動画から輪郭の正解ラベル作成用の静止画を抽出")
    parser.add_argument("--video", required=True, help="判定枠のない元動画")
    parser.add_argument("--output", default="segmentation_annotation_samples")
    parser.add_argument("--interval", type=float, default=30.)
    parser.add_argument("--turn-start", type=float, default=148.)
    parser.add_argument("--turn-end", type=float, default=190.)
    parser.add_argument("--turn-step", type=float, default=2.)
    args = parser.parse_args()

    import cv2

    video = Path(args.video)
    if not video.is_file():
        raise SystemExit(f"元動画が見つかりません: {video}")
    if "YOLO判定" in video.name or "yolo_annotated" in video.name.lower():
        raise SystemExit("YOLO判定枠が描き込まれた動画は学習用にしないでください。元動画を指定してください")
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit("動画を開けません")
    fps = capture.get(cv2.CAP_PROP_FPS)
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    if fps <= 0 or frames <= 0:
        capture.release()
        raise SystemExit("元動画のフレームレート・長さを読み取れません")
    duration = frames / fps
    try:
        timestamps = sampling_seconds(
            duration, args.interval, args.turn_start,
            args.turn_end, args.turn_step)
    except ValueError as exc:
        capture.release()
        raise SystemExit(str(exc)) from exc
    out = Path(args.output)
    if out.exists() and any(out.iterdir()):
        capture.release()
        raise SystemExit("出力フォルダに既存ファイルがあります。上書きせず、新しいフォルダを指定してください")
    out.mkdir(parents=True, exist_ok=True)
    print("【動画の出所確認】学習・検証への重複混入を防ぐため、元動画の識別値を計算します")
    video_sha256 = sha256_file(video)
    manifest = []
    for sec in timestamps:
        # Target frame index is preferable for deterministic extraction and
        # avoids accumulating fractional seek error across multiple frames.
        frame_no = min(int(round(sec * fps)), int(frames)-1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        filename = f"frame_{frame_no:07d}_{sec:07.2f}s.jpg"
        output_file = out / filename
        if not cv2.imwrite(str(output_file), frame, [
                int(cv2.IMWRITE_JPEG_QUALITY), 96]):
            continue
        manifest.append((f"{sec:.3f}", str(frame_no), filename, video_sha256))
    capture.release()
    with (out / "annotation_manifest.csv").open(
            "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("video_seconds", "frame_index", "image",
                         "source_video_sha256"))
        writer.writerows(manifest)
    print(f"【画像の抽出】{len(manifest)}枚 / 保存先: {out}")
    print("【重要】これは未ラベル画像です。車体輪郭を人が囲ってアノテーションしてから学習してください。")
    print("【注意】画面全体・ナンバープレート等の個人情報が含まれる場合は公開前に取り扱いを確認してください。")


if __name__ == "__main__":
    main()
