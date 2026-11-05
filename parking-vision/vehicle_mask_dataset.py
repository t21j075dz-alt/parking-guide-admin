# -*- coding: utf-8 -*-
"""Create a checked YOLO-seg dataset from independently recorded sessions.

Input session folder:
  frame_*.jpg
  labels/frame_*.txt  # saved by annotate_vehicle_masks.py
  annotation_manifest.csv  # source_video_sha256; created by the frame exporter

Use different original-video recordings for train, val and test. One recorded
session is never split across these partitions. No cloud uploads.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path


# Official COCO80 order. KEEP original class IDs so that original YOLO11s-seg
# and fine-tuned YOLO11s-seg can be evaluated on the SAME test annotations.
COCO_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass",
    "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors",
    "teddy bear", "hair drier", "toothbrush",
)
TARGET_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def polygon_area(coords):
    pairs = list(zip(coords[::2], coords[1::2]))
    return abs(sum(x * pairs[(i+1) % len(pairs)][1] -
                   pairs[(i+1) % len(pairs)][0] * y
                   for i, (x, y) in enumerate(pairs))) / 2


def validate_label(text, context="annotation"):
    """Fail closed on box-only labels, wrong classes, bad polygons and NaNs."""
    count = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) < 7 or len(fields) % 2 != 1:
            raise ValueError(f"{context}:{line_number}: 輪郭は3点以上の(x,y)座標を指定してください")
        try:
            class_id = int(fields[0])
            coords = [float(value) for value in fields[1:]]
        except ValueError as exc:
            raise ValueError(f"{context}:{line_number}: 数値を読み取れません") from exc
        if class_id not in TARGET_CLASSES:
            raise ValueError(
                f"{context}:{line_number}: この研究のラベルは{sorted(TARGET_CLASSES)}のみです")
        if not all(math.isfinite(x) and 0. <= x <= 1. for x in coords):
            raise ValueError(f"{context}:{line_number}: 座標は0～1の有限値にしてください")
        if polygon_area(coords) < 1e-6:
            raise ValueError(f"{context}:{line_number}: 輪郭面積が小さすぎます")
        count += 1
    return count


def sha256_file(path):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inspect_session(folder):
    """Return (source_video_hash, [(image,label), ...]) from ONE recording."""
    folder = Path(folder).resolve()
    manifest = folder / "annotation_manifest.csv"
    if not manifest.is_file():
        raise ValueError(f"元動画の記録ファイルがありません: {manifest}")
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"静止画一覧が空です: {manifest}")
    video_hashes = {row.get("source_video_sha256", "").strip() for row in rows}
    if len(video_hashes) != 1 or not next(iter(video_hashes)):
        raise ValueError(
            f"動画出所を確認できません: {manifest}。最新版の画像抽出ツールで再作成してください")
    video_hash = next(iter(video_hashes))
    if len(video_hash) != 64 or any(x not in "0123456789abcdef" for x in video_hash):
        raise ValueError("元動画の識別コードが不正です")
    pairs = []
    seen = set()
    for row in rows:
        filename = Path(row.get("image", ""))
        # Never accept absolute paths or traversal in a manifest.
        if filename.name != str(filename) or filename.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"不正な画像名です: {filename}")
        if filename.name in seen:
            raise ValueError(f"画像が重複しています: {filename}")
        seen.add(filename.name)
        image = folder / filename
        label = folder / "labels" / (filename.stem + ".txt")
        if not image.is_file():
            raise ValueError(f"画像がありません: {image}")
        if not label.is_file():
            raise ValueError(f"未確認・未ラベルの画像があります: {label}")
        validate_label(label.read_text(encoding="utf-8-sig"), str(label))
        pairs.append((image, label))
    return video_hash, pairs


def build_dataset(train, val, test, output):
    sources = {"train": Path(train).resolve(), "val": Path(val).resolve()}
    if test:
        sources["test"] = Path(test).resolve()
    if len(set(sources.values())) != len(sources):
        raise ValueError("train / val / test には別々の元動画フォルダを指定してください")
    destination = Path(output).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("保存先に既存ファイルがあります。別の新しい出力先を指定してください")
    if any(destination == src or destination in src.parents or
           src in destination.parents for src in sources.values()):
        raise ValueError("出力フォルダを元画像フォルダの内側や親に指定しないでください")

    all_sources = {}
    for split, folder in sources.items():
        video_hash, pairs = inspect_session(folder)
        if video_hash in all_sources:
            raise ValueError(
                f"同一の元動画を複数の分割に使用できません: {all_sources[video_hash]} と {split}")
        all_sources[video_hash] = split
        sources[split] = (folder, pairs)

    # Repeated image content is not independent evidence.
    seen_image_hashes = {}
    for split, (_, pairs) in sources.items():
        for image, label in pairs:
            digest = sha256_file(image)
            if digest in seen_image_hashes:
                raise ValueError(f"同じ画像が複数回使用されています: {image}, {seen_image_hashes[digest]}")
            seen_image_hashes[digest] = image

    destination.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split, (_, pairs) in sources.items():
        imgs = destination / "images" / split
        labels = destination / "labels" / split
        imgs.mkdir(parents=True, exist_ok=True)
        labels.mkdir(parents=True, exist_ok=True)
        annotations = 0
        for image, label in pairs:
            shutil.copy2(image, imgs / image.name)
            shutil.copy2(label, labels / label.name)
            annotations += validate_label(label.read_text(encoding="utf-8-sig"),
                                          str(label))
        stats[split] = {"images": len(pairs), "polygons": annotations}
        if annotations == 0:
            raise ValueError(f"{split}には車体輪郭が1つもありません")
    text = [
        "# Split by DIFFERENT source-video recordings; not by neighboring frames.",
        "path: " + json.dumps(destination.as_posix(), ensure_ascii=False),
        "train: images/train", "val: images/val",
    ]
    if test:
        text.append("test: images/test")
    text.extend(["names:"] + [
        "  " + str(i) + ": " + json.dumps(name)
        for i, name in enumerate(COCO_NAMES)])
    (destination / "dataset.yaml").write_text(
        "\n".join(text) + "\n", encoding="utf-8")
    (destination / "dataset_summary.json").write_text(
        json.dumps({"partitions": stats, "classes": TARGET_CLASSES,
                    "notes": "No label is automatic. Only independent sessions."},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return destination / "dataset.yaml", stats


def main():
    parser = argparse.ArgumentParser(
        description="別撮影回に分けたYOLO車体輪郭データセットを作成・検証")
    parser.add_argument("--train", required=True, help="元動画Aの手動ラベル付き画像フォルダ")
    parser.add_argument("--val", required=True, help="元動画Bの手動ラベル付き画像フォルダ")
    parser.add_argument("--test", default=None, help="元動画C: 未使用の独立評価用")
    parser.add_argument("--output", required=True, help="新しい学習データ保存先")
    args = parser.parse_args()
    try:
        yaml_path, stats = build_dataset(
            args.train, args.val, args.test, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"【データセット作成完了】{yaml_path}")
    for split, info in stats.items():
        print(f"  {split}: {info['images']}枚・手動輪郭{info['polygons']}個")
    if not args.test:
        print("【注意】独立したtest用の撮影回が未設定です。最終精度の比較には使用しないでください。")
    print("【注意】YOLOの既存80クラス名を維持していますが、未ラベルのクラスの性能維持は保証できません。")


if __name__ == "__main__":
    main()
