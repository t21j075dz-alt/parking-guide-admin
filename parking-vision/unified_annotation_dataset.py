# -*- coding: utf-8 -*-
"""Shared, review-only ground-truth workspace for YOLO-seg and obstacle detection.

Both tasks share the same source photographs and UI, NEVER the same label schema.
No inference labels are treated as ground truth; blank .txt means a human-reviewed
negative, while no .txt means unreviewed (not allowed in an exported dataset).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

from label_obstacles import CLASS_KEYS as OBSTACLE_NAMES, decode_yolo_line, yolo_line
from vehicle_mask_dataset import COCO_NAMES, validate_label, sha256_file

TASKS = ("vehicle", "obstacle", "layout")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VEHICLE_CLASSES = {2: "乗用車・ミニバン", 3: "二輪車", 5: "バス", 7: "トラック"}
OBSTACLE_CLASSES = dict(enumerate(("カラーコーン", "ショッピングカート",
                                    "バリケード", "車止め・ポール", "その他の障害物")))
# Ground markings are segmentation polygons, NOT the vehicle or obstacle labels.
# A visible area only: never invent hidden bay borders behind parked vehicles.
LAYOUT_NAMES = ("parking_space", "parking_line", "drive_aisle",
                "pedestrian_crossing", "direction_arrow")
LAYOUT_CLASSES = dict(enumerate(("駐車枠の見える床面", "白線・区画線",
                                 "車両通路の見える路面", "横断歩道", "進行方向の矢印")))


def validate_obstacles(text, context="obstacle"):
    count = 0
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            decode_yolo_line(line)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"{context}:{n}: 不正な障害物の正解枠") from exc
        count += 1
    return count


def validate_layout(text, context="layout"):
    # Separate from COCO80 vehicle IDs, requiring at least three polygon vertices.
    from vehicle_mask_dataset import polygon_area
    count = 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 7 or len(parts) % 2 != 1:
            raise ValueError(f"{context}:{number}: 区画・路面は3点以上の輪郭で指定")
        try:
            category = int(parts[0])
            coords = [float(v) for v in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"{context}:{number}: 数値が不正です") from exc
        if category not in LAYOUT_CLASSES or not all(
                math.isfinite(v) and 0 <= v <= 1 for v in coords):
            raise ValueError(f"{context}:{number}: 種類・座標が不正です")
        if polygon_area(coords) < 1e-6:
            raise ValueError(f"{context}:{number}: 輪郭の面積が小さすぎます")
        count += 1
    return count


def layout_polygon_to_yolo(class_id, points, width, height):
    if class_id not in LAYOUT_CLASSES or width <= 0 or height <= 0 or len(points) < 3:
        raise ValueError("路面の輪郭は3点以上で指定してください")
    coordinates = []
    for x, y in points:
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("画像の外には点を置けません")
        coordinates.extend([x / width, y / height])
    line = str(class_id) + " " + " ".join(f"{v:.6f}" for v in coordinates)
    validate_layout(line)
    return line


def layout_to_polygon(line, width, height):
    validate_layout(line)
    fields = line.split()
    return int(fields[0]), [
        (min(width - 1, round(float(fields[i]) * width)),
         min(height - 1, round(float(fields[i + 1]) * height)))
        for i in range(1, len(fields), 2)]


def validate_task_label(task, text, context="label"):
    if task == "vehicle":
        return validate_label(text, context)
    if task == "obstacle":
        return validate_obstacles(text, context)
    if task == "layout":
        return validate_layout(text, context)
    raise ValueError(f"未対応の種類: {task}")


def image_id(relative):
    # Stable across rescans of the same source folder; no non-ASCII Windows paths.
    return "img_" + hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:20]


def list_photos(images_root, *, workspace=None):
    images_root = Path(images_root).expanduser().resolve()
    if not images_root.is_dir():
        raise ValueError(f"写真フォルダがありません: {images_root}")
    if workspace is not None:
        workspace = Path(workspace).expanduser().resolve()
        if workspace == images_root or workspace.is_relative_to(images_root):
            raise ValueError("作業用フォルダは元写真の外側に指定してください")
    photos = []
    for path in sorted(images_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            relative = path.relative_to(images_root)
            photos.append({"id": image_id(relative), "path": path,
                           "relative": relative})
    if not photos:
        raise ValueError(f"画像がありません: {images_root}")
    if len({p["id"] for p in photos}) != len(photos):
        raise ValueError("画像識別番号が重複しています")
    return photos


class AnnotationWorkspace:
    def __init__(self, images_root, workspace):
        self.images_root = Path(images_root).expanduser().resolve()
        self.workspace = Path(workspace).expanduser().resolve()
        self.photos = list_photos(self.images_root, workspace=self.workspace)
        marker = self.workspace / "source.json"
        if marker.is_file():
            source = json.loads(marker.read_text(encoding="utf-8"))
            if source.get("images_root") != str(self.images_root):
                raise ValueError("別の写真フォルダの作業データを上書きできません")
        else:
            if self.workspace.exists() and any(self.workspace.iterdir()):
                raise ValueError("別用途のデータがある作業フォルダは使えません")
            self.workspace.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps(
                {"images_root": str(self.images_root),
                 "notes": "Explicit human labels ONLY. No auto-generated ground truth."},
                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def label_path(self, photo, task):
        if task not in TASKS:
            raise ValueError(f"不明なタスク: {task}")
        return self.workspace / "labels" / task / (photo["id"] + ".txt")

    def is_reviewed(self, photo, task):
        return self.label_path(photo, task).is_file()

    def read(self, photo, task):
        label = self.label_path(photo, task)
        if not label.exists():
            return "", False
        value = label.read_text(encoding="utf-8-sig")
        validate_task_label(task, value, str(label))
        return value, True

    def save(self, photo, task, content):
        validate_task_label(task, content)
        path = self.label_path(photo, task)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".txt.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def progress(self):
        return {task: sum(self.is_reviewed(p, task) for p in self.photos)
                for task in TASKS}

    def next_unreviewed(self, start=0):
        for index in list(range(start, len(self.photos))) + list(range(0, start)):
            if any(not self.is_reviewed(self.photos[index], task) for task in TASKS):
                return index
        return None


def export_dataset(train_workspace, task, output,
                   val_workspace=None, test_workspace=None,
                   allow_train_only=False):
    """Export only explicitly reviewed images. Never split one session randomly."""
    if task not in TASKS:
        raise ValueError(f"未知の種類: {task}")
    if not val_workspace and not allow_train_only:
        raise ValueError("独立した検証写真が必要です。試験のみなら--train-onlyを指定")
    if test_workspace and not val_workspace:
        raise ValueError("テストだけを渡すことはできません")
    groups = {"train": train_workspace}
    if val_workspace:
        groups["val"] = val_workspace
    if test_workspace:
        groups["test"] = test_workspace
    roots = [item.images_root for item in groups.values()]
    if len(set(roots)) != len(roots):
        raise ValueError("train/val/testを同じ元写真フォルダから作ることはできません")
    for i, a in enumerate(roots):
        for b in roots[i + 1:]:
            if a.is_relative_to(b) or b.is_relative_to(a):
                raise ValueError("train/val/testは重複する親子フォルダを使えません")
    output = Path(output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("既存の学習データセットを上書きしません")
    for ws in groups.values():
        if output == ws.workspace or output.is_relative_to(ws.workspace) or \
                output == ws.images_root or output.is_relative_to(ws.images_root):
            raise ValueError("学習データセット出力先は元画像・作業フォルダの外に指定")
    # Validate everything BEFORE writing any output.
    manifest = {}
    seen_hashes = {}
    for split, ws in groups.items():
        records = []
        for p in ws.photos:
            text, reviewed = ws.read(p, task)
            if not reviewed:
                raise ValueError(
                    f"{split}: 未確認画像があります（{p['relative']}）。全対象を登録、"
                    "もしくは別の使用可能写真フォルダに移してください")
            image_hash = sha256_file(p["path"])
            if image_hash in seen_hashes:
                raise ValueError(f"画像の重複: {p['relative']} と {seen_hashes[image_hash]}")
            seen_hashes[image_hash] = str(p["path"])
            records.append((p, text, image_hash))
        if not records:
            raise ValueError(f"{split}の写真がありません")
        if sum(validate_task_label(task, record[1]) for record in records) == 0:
            raise ValueError(f"{split}に{task}の正例がありません")
        manifest[split] = records

    output.mkdir(parents=True, exist_ok=True)
    stats = {}
    rows = []
    for split, records in manifest.items():
        images_dir = output / "images" / split
        labels_dir = output / "labels" / split
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for photo, text, image_hash in records:
            basename = photo["id"]
            image_name = basename + photo["path"].suffix.lower()
            shutil.copy2(photo["path"], images_dir / image_name)
            (labels_dir / (basename + ".txt")).write_text(text, encoding="utf-8")
            count += validate_task_label(task, text)
            rows.append((split, photo["relative"].as_posix(), image_name, image_hash))
        stats[split] = {"images": len(records), "objects": count}
    with (output / "provenance.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("split", "relative_original", "dataset_image", "sha256"))
        writer.writerows(rows)
    names = (COCO_NAMES if task == "vehicle" else
             OBSTACLE_NAMES if task == "obstacle" else LAYOUT_NAMES)
    yaml_lines = ["# Verified human labels; session-separated splits",
                  "path: " + json.dumps(output.as_posix(), ensure_ascii=False),
                  "train: images/train",
                  "val: images/val" if val_workspace else "val: images/train"]
    if test_workspace:
        yaml_lines.append("test: images/test")
    yaml_lines += ["names:"] + [
        f"  {index}: {json.dumps(name)}" for index, name in enumerate(names)]
    (output / "dataset.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (output / "dataset_summary.json").write_text(json.dumps(
        {"task": task, "splits": stats, "independent_validation": bool(val_workspace),
         "training_only": not bool(val_workspace),
         "warning": "train-only datasets do not support accuracy claims"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "dataset.yaml", stats


def workspace_source(workspace, override=None):
    """Find the source folder recorded at annotation time."""
    if override:
        return override
    marker = Path(workspace).expanduser().resolve() / "source.json"
    if not marker.is_file():
        raise ValueError(f"作業フォルダにsource.jsonがありません: {marker}")
    root = json.loads(marker.read_text(encoding="utf-8")).get("images_root")
    if not root:
        raise ValueError("元写真の保存先が記録されていません")
    return root


def export_cli(argv):
    parser = argparse.ArgumentParser(description="統合ラベルのYOLOデータセット書き出し")
    parser.add_argument("--mode", choices=TASKS, required=True)
    parser.add_argument("--train-images", help="省略すると作業フォルダから元写真の場所を復元")
    parser.add_argument("--train-workspace", required=True)
    parser.add_argument("--val-images")
    parser.add_argument("--val-workspace")
    parser.add_argument("--test-images")
    parser.add_argument("--test-workspace")
    parser.add_argument("--output", required=True)
    parser.add_argument("--train-only", action="store_true",
                        help="独立検証なしの試験データ。精度スコアの評価は禁止")
    args = parser.parse_args(argv)
    if args.val_images and not args.val_workspace:
        parser.error("val-imagesを指定するときはval-workspaceも必要です")
    if args.test_images and not args.test_workspace:
        parser.error("test-imagesを指定するときはtest-workspaceも必要です")
    try:
        train = AnnotationWorkspace(
            workspace_source(args.train_workspace, args.train_images), args.train_workspace)
        val = (AnnotationWorkspace(
            workspace_source(args.val_workspace, args.val_images), args.val_workspace)
               if args.val_workspace else None)
        test = (AnnotationWorkspace(
            workspace_source(args.test_workspace, args.test_images), args.test_workspace)
                if args.test_workspace else None)
        yaml, counts = export_dataset(
            train, args.mode, args.output, val_workspace=val, test_workspace=test,
            allow_train_only=args.train_only)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print("【出力完了】", yaml)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    if not val:
        print("【注意】訓練専用。独立した検証データはありません。学習時はval=Falseにしてください")


if __name__ == "__main__":
    import sys
    export_cli(sys.argv[1:])
