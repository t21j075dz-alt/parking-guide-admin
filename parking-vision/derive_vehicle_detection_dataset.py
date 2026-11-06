# -*- coding: utf-8 -*-
"""Re-use HUMAN-REVIEWED vehicle masks as vehicle detection boxes (no re-labeling).

Never turn model predictions into ground truth. This exporter only transforms
already verified YOLO-seg polygons to their enclosing YOLO-detect rectangles.
No GPU, camera access, Supabase, or active model changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path

from vehicle_mask_dataset import COCO_NAMES, sha256_file, validate_label

EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def polygon_to_box(line: str) -> str:
    """An exact rectangular enclosure of a verified normalized polygon."""
    validate_label(line, "vehicle segment")
    fields = line.split()
    category = int(fields[0])
    points = [float(v) for v in fields[1:]]
    xs, ys = points[::2], points[1::2]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    width, height = x2 - x1, y2 - y1
    if not (width > 1e-6 and height > 1e-6 and all(math.isfinite(v)
                                                   for v in (x1, x2, y1, y2))):
        raise ValueError("極端に細い車両輪郭は検出枠に変換できません")
    return f"{category} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {width:.6f} {height:.6f}"


def prepare(source, output):
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    summary_path = source / "dataset_summary.json"
    if not summary_path.is_file():
        raise ValueError("統合画面で書き出したvehicleデータセットを指定してください")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("task") != "vehicle":
        raise ValueError("車体輪郭のデータセット以外から検出枠を作れません")
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("出力先と元データセットを別フォルダにしてください")
    if output.exists() and any(output.iterdir()):
        raise ValueError("既存の出力データセットを上書きできません")
    splits = list(summary.get("splits", {}))
    if not splits or "train" not in splits:
        raise ValueError("trainの正解データがありません")
    if "val" in splits and not summary.get("independent_validation", False):
        raise ValueError("同一撮影画像を検証用と誤認しないでください")
    prepared = {}
    hashes = set()
    for split in splits:
        images = source / "images" / split
        labels = source / "labels" / split
        if not images.is_dir() or not labels.is_dir():
            raise ValueError(f"{split}の画像・ラベルがありません")
        frames = sorted(p for p in images.iterdir()
                        if p.is_file() and p.suffix.lower() in EXTENSIONS)
        if not frames:
            raise ValueError(f"{split}には写真がありません")
        if len({p.stem for p in frames}) != len(frames):
            raise ValueError("同一ファイル名の異なる画像が混在しています")
        translated, nobjects = [], 0
        for frame in frames:
            label = labels / (frame.stem + ".txt")
            if not label.is_file():
                raise ValueError(f"正解ラベルがありません: {label}")
            contents = label.read_text(encoding="utf-8-sig")
            validate_label(contents, str(label))
            boxes = [polygon_to_box(line) for line in contents.splitlines() if line.strip()]
            nobjects += len(boxes)
            file_hash = sha256_file(frame)
            if file_hash in hashes:
                raise ValueError(f"同じ画像が重複しています: {frame.name}")
            hashes.add(file_hash)
            translated.append((frame, boxes))
        expected = summary["splits"].get(split, {})
        if len(frames) != expected.get("images") or nobjects != expected.get("objects"):
            raise ValueError(f"{split}の元データ記録と画像・車両個数が違います")
        if not nobjects:
            raise ValueError(f"{split}に車両の正例がありません")
        prepared[split] = (translated, nobjects)

    output.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split, (records, count) in prepared.items():
        image_dst = output / "images" / split
        label_dst = output / "labels" / split
        image_dst.mkdir(parents=True)
        label_dst.mkdir(parents=True)
        for image, boxes in records:
            shutil.copy2(image, image_dst / image.name)
            (label_dst / (image.stem + ".txt")).write_text(
                "\n".join(boxes) + ("\n" if boxes else ""), encoding="utf-8")
        stats[split] = {"images": len(records), "objects": count}
    lines = ["# Auto-derived from human-verified vehicle segment polygons",
             "path: " + json.dumps(output.as_posix(), ensure_ascii=False),
             "train: images/train",
             "val: images/val" if "val" in prepared else "val: images/train"]
    if "test" in prepared:
        lines.append("test: images/test")
    lines += ["names:"] + [
        f"  {i}: {json.dumps(name)}" for i, name in enumerate(COCO_NAMES)]
    (output / "dataset.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "dataset_summary.json").write_text(json.dumps({
        "task": "vehicle_detect",
        "source_task": "vehicle",
        "derived_from_reviewed_vehicle_polygons": True,
        "source_dataset": str(source),
        "splits": stats,
        "independent_validation": summary.get("independent_validation", False),
        "training_only": not summary.get("independent_validation", False),
        "note": "Derived boxes, not new labels; do not claim new scene diversity",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if (source / "provenance.csv").is_file():
        shutil.copy2(source / "provenance.csv", output / "provenance.csv")
    return output / "dataset.yaml", stats


def main():
    parser = argparse.ArgumentParser(
        description="手動登録した車両輪郭を追加作業なしでYOLO検出枠へ自動変換")
    parser.add_argument("--source",
                        default="reviewed_photo_datasets/vehicle_242_pilot")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        path, stats = prepare(args.source, args.output)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print("【車両検出枠へ自動変換完了】", path)
    print(json.dumps(stats, ensure_ascii=False))
    print("【注意】同じ241枚から生成した別形式のラベル。精度向上の証明ではありません")


if __name__ == "__main__":
    main()
