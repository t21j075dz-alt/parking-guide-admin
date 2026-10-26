#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""カラーコーン・ショッピングカートなどを追加学習する。

画像に正解の四角を描いた後、まずデータを検査してから学習を開始する。
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys


def check_dataset(yaml_path: str) -> dict:
    """誤ったデータを大量に学習させないために正解枠を点検する。"""
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("PyYAMLが必要です。python -m pip install -r requirements.txt") from exc
    settings_path = Path(yaml_path).expanduser().resolve()
    if not settings_path.is_file():
        raise ValueError("data.yaml が見つかりません。先に label_obstacles.py で正解枠を登録してください")
    config = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("names"), dict):
        raise ValueError("data.yaml の names が正しくありません")
    num_classes = len(config["names"])
    if not num_classes:
        raise ValueError("学習する物体の種類が未設定です")
    base = Path(config.get("path") or settings_path.parent).expanduser()
    if not base.is_absolute():
        # Ultralyticsと同様に、実行フォルダが基準のファイルを先に確認。
        base = (Path.cwd() / base).resolve()
        if not base.is_dir():
            base = (settings_path.parent / (config.get("path") or ".")).resolve()
    results = {}
    for subset in ("train", "val"):
        images_ref = config.get(subset)
        if not isinstance(images_ref, str) or not images_ref.startswith("images/"):
            raise ValueError(subset + " は images/train や images/val の形式にしてください")
        img_dir = base / images_ref
        label_dir = base / ("labels/" + images_ref.removeprefix("images/"))
        images = [p for p in img_dir.iterdir() if p.suffix.lower() in
                  {".jpg", ".jpeg", ".png", ".bmp", ".webp"}] if img_dir.is_dir() else []
        if not images:
            raise ValueError(str(img_dir) + " に学習・検証用の写真がありません")
        categories = Counter()
        labeled_images = 0
        for image in images:
            label = label_dir / (image.stem + ".txt")
            if not label.is_file():
                raise ValueError(str(image.name) + " に正解ラベルがありません。写真の登録を確認してください")
            lines = [line for line in label.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                labeled_images += 1
            for line in lines:
                fields = line.split()
                try:
                    cls = int(fields[0])
                    values = list(map(float, fields[1:]))
                    if len(fields) != 5 or cls not in range(num_classes):
                        raise ValueError()
                    x, y, w, h = values
                    if w <= 0 or h <= 0 or not (
                        0 <= x - w/2 <= x + w/2 <= 1.000001 and
                        0 <= y - h/2 <= y + h/2 <= 1.000001
                    ):
                        raise ValueError()
                except (ValueError, IndexError) as exc:
                    raise ValueError(str(label) + " の正解枠が不正です: " + line) from exc
                categories[cls] += 1
        if not categories:
            raise ValueError(subset + " の写真に学習対象が1つもありません。カラーコーンなどの実物を撮影し、正解の四角を描いてください")
        results[subset] = {"images": len(images), "images_with_objects": labeled_images,
                           "class_box_counts": dict(categories)}
    for class_id in results["train"]["class_box_counts"]:
        if not results["val"]["class_box_counts"].get(class_id):
            print("注意：種類 " + str(config["names"].get(class_id, class_id))
                  + " に検証用の実物写真がありません。性能確認には別途撮影が必要です。")
    return results


def main():
    parser = argparse.ArgumentParser(description="正解ラベルを確認してカラーコーン・カートなどを追加学習")
    parser.add_argument("--data", default="dataset/data.yaml", help="写真と正解ラベルを記述したファイル")
    parser.add_argument("--base", default="yolo11n.pt", help="初期モデル（独自のbest.ptも指定可能）")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--device", default="cpu", help="CPUはcpu、CUDA GPUは0")
    args = parser.parse_args()
    if args.epochs < 1 or args.epochs > 500:
        sys.exit("学習回数は1～500に設定してください")
    try:
        counts = check_dataset(args.data)
    except ValueError as exc:
        sys.exit("写真の正解枠を確認してください: " + str(exc))
    print("学習用写真", counts["train"]["images"], "枚／正解あり", counts["train"]["images_with_objects"], "枚")
    print("検証用写真", counts["val"]["images"], "枚／正解あり", counts["val"]["images_with_objects"], "枚")
    print("※精度は学習用と異なる日・別の場所の写真で評価してください。")
    try:
        from ultralytics import YOLO
    except ImportError:
        sys.exit("YOLOが見つかりません。python -m pip install -r requirements.txt を実行してください")
    model = YOLO(args.base)
    model.train(data=str(Path(args.data).expanduser().resolve()), epochs=args.epochs,
                imgsz=640, batch=8, device=args.device,
                project="runs/parking-obstacles", name="experiment")
    directory = getattr(getattr(model, "trainer", None), "save_dir", None)
    print("学習終了。検証結果を見てから使ってください。")
    if directory:
        print("学習済みモデル:", Path(directory) / "weights" / "best.pt")


if __name__ == "__main__":
    main()
