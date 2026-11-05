# -*- coding: utf-8 -*-
"""Baseline vs custom YOLO-seg: independent human-labeled test masks only.

Comparison is an offline report. It never changes a model configuration,
the live parking state, or user application.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract_segmentation_metrics(metrics):
    if getattr(metrics, "seg", None) is None:
        raise ValueError("セグメンテーションの評価指標がありません")
    seg = metrics.seg
    box = getattr(metrics, "box", None)
    return {
        "mask_map50_95": float(seg.map),
        "mask_map50": float(seg.map50),
        "mask_map75": float(seg.map75),
        "box_map50_95": float(box.map) if box is not None else None,
    }


def ensure_test_split(dataset_yaml):
    path = Path(dataset_yaml).resolve()
    if not path.is_file():
        raise ValueError(f"dataset.yamlがありません: {path}")
    # PyYAML is already an Ultralytics dependency.
    import yaml
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict) or not data.get("test"):
        raise ValueError(
            "独立したtest用動画が指定されていません。"
            "学習用・検証用とは別の日または撮影回の画像を用意してください")
    if "names" not in data or len(data["names"]) != 80:
        raise ValueError("既存COCO80分類と一致するdataset.yamlを使用してください")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="独立テスト用の正解輪郭でHigh標準と追加学習モデルを公平比較")
    parser.add_argument("--data", required=True)
    parser.add_argument("--candidate", required=True, help="学習で得られたbest.pt")
    parser.add_argument("--baseline", default="yolo11s-seg.pt")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output", default="runs/vehicle_segmentation_comparison.json")
    args = parser.parse_args()
    try:
        data = ensure_test_split(args.data)
    except ValueError as exc:
        parser.error(str(exc))
    if not Path(args.candidate).is_file():
        parser.error("学習済みのbest.ptを指定してください。未学習モデルを評価できません")
    if args.imgsz < 256 or args.imgsz > 1920 or args.batch < 1:
        parser.error("imgszは256～1920、batchは1以上にしてください")
    from ultralytics import YOLO
    models = {"baseline": args.baseline, "candidate": args.candidate}
    results = {}
    for role, weights in models.items():
        model = YOLO(weights)
        if getattr(model, "task", None) != "segment":
            raise ValueError(f"{role}: segmentモデルが必要です")
        kwargs = dict(data=str(data), split="test", imgsz=args.imgsz,
                      batch=args.batch, workers=0, plots=False, verbose=False)
        if args.device != "auto":
            kwargs["device"] = args.device
        print(f"【独立テスト】{role} / {weights}")
        metrics = model.val(**kwargs)
        results[role] = {
            "model": str(weights),
            **extract_segmentation_metrics(metrics),
        }
    result = {
        "dataset": str(data), "split": "test", "imgsz": args.imgsz,
        "baseline": results["baseline"],
        "candidate": results["candidate"],
        "delta_mask_map50_95":
            results["candidate"]["mask_map50_95"] -
            results["baseline"]["mask_map50_95"],
        "notes": [
            "同じ手動正解データ・同じ入力画像サイズで比較しています",
            "測定指標はCOCO形式のマスクmAPであり駐車位置認識の正答率ではありません",
            "精度・速度・区画判定を実録画でも比較するまで、実運用には組み込みません",
            "学習時と同じ録画の隣接フレームでは汎化性能を評価できません",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise SystemExit("結果ファイルが既に存在します。別名にして上書きを避けてください")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    print(f"【比較完了】{output}")
    print(f"【マスクmAP50-95差】{result['delta_mask_map50_95']:+.4f}")
    print("【注意】プラスでも運用採用は自動では行いません。車種別・撮影角度別の目視確認が必要です。")


if __name__ == "__main__":
    main()
