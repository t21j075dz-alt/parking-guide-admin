# -*- coding: utf-8 -*-
"""One-frame YOLO11 segmentation PILOT + separate obstacle-photo preparation.

A single frame cannot establish accuracy. No cloud writes or active model changes.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from vehicle_mask_dataset import COCO_NAMES, sha256_file, validate_label


def select_first(session):
    session = Path(session).expanduser().resolve()
    manifest = session / "annotation_manifest.csv"
    if not manifest.is_file():
        raise ValueError("annotation_manifest.csv がありません")
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("元動画から抽出した画像がありません")
    hashes = {r.get("source_video_sha256", "") for r in rows}
    if len(hashes) != 1:
        raise ValueError("複数の元動画が混在しています")
    video_hash = next(iter(hashes))
    if len(video_hash) != 64 or any(c not in "0123456789abcdef" for c in video_hash):
        raise ValueError("元動画SHA256の記録が不正です")
    for row in rows:
        name = row.get("image", "")
        if Path(name).name != name or Path(name).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            raise ValueError("画像ファイル名が不正です")
    first = min(rows, key=lambda r: int(r.get("frame_index", "-1")))
    image = session / first["image"]
    label = session / "labels" / (image.stem + ".txt")
    if not image.is_file() or not label.is_file():
        raise ValueError(f"画像または正解ラベルがありません: {image.name}")
    count = validate_label(label.read_text(encoding="utf-8-sig"), str(label))
    if count <= 0:
        raise ValueError("最初の画像に車両輪郭ラベルがありません")
    return image, label, video_hash, count


def empty_output(output, source):
    output = Path(output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("出力先にファイルがあります。既存の学習データを上書きしません")
    source = Path(source).resolve()
    if output == source or output in source.parents or source in output.parents:
        raise ValueError("画像が入った元フォルダと出力先を分離してください")
    return output


def prepare_seg(session, output):
    image, label, video_hash, count = select_first(session)
    output = empty_output(output, image.parent)
    images = output / "images" / "train"
    labels = output / "labels" / "train"
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, images / image.name)
    shutil.copy2(label, labels / label.name)
    # Ultralytics data.yaml requires a val entry. It is a format-only placeholder.
    # The real training command uses val=False; this is NOT independent validation.
    yaml = ["# ONE IMAGE PILOT: val=train is NOT an accuracy test",
            "path: " + json.dumps(output.as_posix(), ensure_ascii=False),
            "train: images/train", "val: images/train", "names:"]
    yaml.extend(f"  {i}: {json.dumps(name)}" for i, name in enumerate(COCO_NAMES))
    (output / "dataset.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    (output / "pilot_metadata.json").write_text(json.dumps({
        "type": "single_frame_segmentation_pilot",
        "source_video_sha256": video_hash,
        "source_image": image.name,
        "source_image_sha256": sha256_file(image),
        "polygons": count,
        "independent_validation": False,
        "note": "Never report mAP or deploy this pilot as an improvement"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "dataset.yaml", count


def prepare_obstacles(session, output):
    image, _, video_hash, _ = select_first(session)
    output = empty_output(output, image.parent)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image, output / image.name)
    (output / "source_info.json").write_text(json.dumps({
        "source_video_sha256": video_hash,
        "source_image": image.name,
        "annotation_status": "unlabeled_obstacles",
        "warning": "Do not copy vehicle-mask labels into obstacle labels"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / image.name


def train_pilot(data, model_path="yolo11s-seg.pt", epochs=20, imgsz=960,
                device="auto", name="nikko_firstframe_pilot"):
    data = Path(data).expanduser().resolve()
    marker = data.parent / "pilot_metadata.json"
    if not data.is_file() or not marker.is_file():
        raise ValueError("先にprepare-segで専用データセットを作成してください")
    meta = json.loads(marker.read_text(encoding="utf-8"))
    if meta.get("type") != "single_frame_segmentation_pilot":
        raise ValueError("別のデータセットはこの試験コマンドで学習できません")
    if not (1 <= epochs <= 100 and 320 <= imgsz <= 1280):
        raise ValueError("epochsは1～100、imgszは320～1280で指定してください")
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("学習結果の名前が不正です")
    from ultralytics import YOLO
    model = YOLO(model_path)
    if model.task != "segment":
        raise ValueError("YOLOセグメンテーションモデル(-seg.pt)が必要です")
    if device == "auto":
        import torch
        device = 0 if torch.cuda.is_available() else "cpu"
    print("【1枚のみの試験】検証データはありません。精度改善とは判定できません。")
    print("【安全】稼働モデル・Supabase・アプリの設定は変更しません。")
    model.train(data=str(data), epochs=epochs, imgsz=imgsz, batch=1,
                device=device, workers=0, seed=42, deterministic=True,
                project=str(Path(__file__).resolve().parent / "runs" / "vehicle_segmentation"),
                name=name, exist_ok=False, val=False, plots=False, save=True,
                mosaic=0.0, mixup=0.0, copy_paste=0.0, lr0=0.0001)
    folder = getattr(getattr(model, "trainer", None), "save_dir", None)
    print("【試験学習の保存先】", folder or "runs/vehicle_segmentation")
    print("【注意】last.ptは未検証モデルです。本番には使用しないでください。")


def main():
    parser = argparse.ArgumentParser(description="1枚目の車体輪郭を試験学習 / 障害物の写真を用意")
    commands = parser.add_subparsers(dest="command", required=True)
    for action in ("prepare-seg", "prepare-obstacles"):
        cmd = commands.add_parser(action)
        cmd.add_argument("--session", default="vehicle_mask_sessions/nikko_01")
        cmd.add_argument("--output", required=True)
    train = commands.add_parser("train")
    train.add_argument("--data", required=True)
    train.add_argument("--model", default="yolo11s-seg.pt")
    train.add_argument("--epochs", type=int, default=20)
    train.add_argument("--imgsz", type=int, default=960)
    train.add_argument("--device", default="auto")
    train.add_argument("--name", default="nikko_firstframe_pilot")
    args = parser.parse_args()
    try:
        if args.command == "prepare-seg":
            yaml, count = prepare_seg(args.session, args.output)
            print(f"【準備完了】{count}個の輪郭 / {yaml}")
            print("【注意】val=trainは形式上の参照だけで、独立した精度評価ではありません")
        elif args.command == "prepare-obstacles":
            image = prepare_obstacles(args.session, args.output)
            print("【障害物用の未ラベル画像】", image)
            print("label_obstacles.pyで別の正解枠を付けてください")
        else:
            train_pilot(args.data, args.model, args.epochs, args.imgsz, args.device, args.name)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
