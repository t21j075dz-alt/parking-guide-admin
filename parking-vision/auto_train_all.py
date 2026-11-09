# -*- coding: utf-8 -*-
"""Safe one-command sequential training of THREE tasks from 241 reviewed images.

Vehicle mask -> obstacle bbox -> vehicle bbox derived from the mask polygons.
Never uploads data, touches Supabase, or replaces a live model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from derive_vehicle_detection_dataset import prepare as derive_boxes


ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "vehicle": ROOT / "reviewed_photo_datasets" / "vehicle_242_pilot",
    "obstacle": ROOT / "reviewed_photo_datasets" / "obstacle_242_pilot",
    "vehicle_detect": ROOT / "reviewed_photo_datasets" / "vehicle_detect_auto_v1",
}


def check_source(folder, task):
    folder = Path(folder).resolve()
    summary = folder / "dataset_summary.json"
    yaml = folder / "dataset.yaml"
    if not summary.is_file() or not yaml.is_file():
        raise ValueError(f"{task}の登録データがありません: {folder}")
    data = json.loads(summary.read_text(encoding="utf-8"))
    stats = data.get("splits", {}).get("train", {})
    if data.get("task") != task or stats.get("images", 0) <= 0 or stats.get("objects", 0) <= 0:
        raise ValueError(f"{task}の教師データ数を確認してください: {folder}")
    if data.get("independent_validation", False):
        raise ValueError("この一括試験は独立valなしの241枚向けです。通常学習を使用してください")
    return data


def prepare_derived(source=DEFAULTS["vehicle"], destination=DEFAULTS["vehicle_detect"]):
    source_meta = check_source(source, "vehicle")
    destination = Path(destination).resolve()
    if (destination / "dataset_summary.json").is_file():
        result = check_source(destination, "vehicle_detect")
        if (result.get("source_dataset") != str(Path(source).resolve())
                or result.get("splits", {}).get("train") != source_meta["splits"]["train"]):
            raise ValueError("既存の派生検出データは別の元データから作成されています")
    else:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("派生データセットの出力先が使用済みです")
        derive_boxes(source, destination)
    return destination


def commands(epochs=40, imgsz=960, batch=2, device="auto"):
    if not (1 <= epochs <= 300 and 320 <= imgsz <= 1536 and 1 <= batch <= 16):
        raise ValueError("epochs/imgsz/batchの値を確認してください")
    actions = [
        ("vehicle", "yolo11s-seg.pt", "lighting", "vehicle_lighting_auto_v1"),
        ("obstacle", "yolo11n.pt", "parking", "obstacle_auto_v1"),
        ("vehicle_detect", "yolo11n.pt", "parking", "vehicle_box_auto_v1"),
    ]
    result = []
    for task, model, profile, name in actions:
        data = DEFAULTS[task] / "dataset.yaml"
        cmd = [sys.executable, str(ROOT / "train_reviewed_photos.py"),
               "--task", task, "--data", str(data),
               "--model", model, "--auto-augment", profile,
               "--epochs", str(epochs), "--imgsz", str(imgsz),
               "--batch", str(batch), "--device", device,
               "--name", name, "--accept-train-only"]
        result.append((task, cmd))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="241枚の既存教師ラベルから3種類のYOLOを順番に自動学習（本番反映なし）")
    parser.add_argument("--run", action="store_true",
                        help="GPU学習を本当に始める。省略時は計画表示のみ")
    parser.add_argument("--allow-cpu", action="store_true",
                        help="CUDAが使えないPCでCPU実行を明示的に許可")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    try:
        check_source(DEFAULTS["vehicle"], "vehicle")
        check_source(DEFAULTS["obstacle"], "obstacle")
        steps = commands(args.epochs, args.imgsz, args.batch, args.device)
        for task, cmd in steps:
            print(f"【{task}】", " ".join(cmd), flush=True)
        if not args.run:
            print("【確認のみ】実際に学習する場合は --run を付けてください")
            return
        import torch
        cuda = torch.cuda.is_available()
        if not cuda and not args.allow_cpu:
            raise ValueError("CUDA対応GPUが見つかりません。CPUで実行する場合は--allow-cpu")
        if args.device == "auto" and not cuda and args.allow_cpu:
            steps = commands(args.epochs, args.imgsz, args.batch, "cpu")
        # Derive boxes before the first GPU run. Never replace existing labels.
        prepare_derived()
        print("【自動変換完了】既存の車体輪郭から車両検出枠を準備しました", flush=True)
        print("【重要】すべて独立検証なしの試験。稼働モデルは変更しません", flush=True)
        for task, cmd in steps:
            print(f"【開始】{task}", flush=True)
            subprocess.run(cmd, check=True, cwd=str(ROOT))
            print(f"【終了】{task}", flush=True)
        print("【3種類の試験学習完了】独立した動画で比較するまで本番には反映しません")
    except (ValueError, OSError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
