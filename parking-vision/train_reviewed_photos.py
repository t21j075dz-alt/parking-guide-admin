# -*- coding: utf-8 -*-
"""Fine-tune YOLO using reviewed unified-annotator datasets, never the live model.

Training-only datasets require explicit approval and use val=False.
Each task is trained separately: vehicle=YOLO segment, obstacle=YOLO detect.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def prepare_options(dataset, task, *, epochs=40, imgsz=960, batch=2,
                    name=None, accept_train_only=False):
    data = Path(dataset).expanduser().resolve()
    if not data.is_file():
        raise ValueError(f"dataset.yamlがありません: {data}")
    meta = data.parent / "dataset_summary.json"
    if not meta.is_file():
        raise ValueError("統合ラベルから作ったdataset_summary.jsonが必要です")
    details = json.loads(meta.read_text(encoding="utf-8"))
    if details.get("task") != task or task not in ("vehicle", "obstacle", "layout"):
        raise ValueError("データセットと学習対象が一致しません")
    if not (1 <= epochs <= 500 and 320 <= imgsz <= 1536 and 1 <= batch <= 32):
        raise ValueError("epochs/imgsz/batchは許可範囲内で指定してください")
    has_val = bool(details.get("independent_validation", False))
    if not has_val and not accept_train_only:
        raise ValueError("独立した検証データがありません。"
                         "試験学習する場合のみ --accept-train-only を指定")
    if not name:
        name = task + "_reviewed_v1"
    if name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError("学習名にフォルダ区切りは使えません")
    if not isinstance(details.get("splits"), dict) or \
            details["splits"].get("train", {}).get("images", 0) <= 0 or \
            details["splits"]["train"].get("objects", 0) <= 0:
        raise ValueError("学習対象の正解ラベルがありません")
    if has_val and details["splits"].get("val", {}).get("objects", 0) <= 0:
        raise ValueError("検証用の正例がありません")
    return {
        "data": str(data), "epochs": int(epochs), "imgsz": int(imgsz),
        "batch": int(batch), "workers": 0, "seed": 42, "deterministic": True,
        "project": str(Path(__file__).resolve().parent / "runs" / "unified_training"),
        "name": name, "exist_ok": False,
        "val": has_val, "save": True,
        "plots": has_val, "patience": 20,
    }, has_val


def main():
    parser = argparse.ArgumentParser(
        description="手動で確認した242枚等を使い、車体輪郭と障害物を別々に追加学習")
    parser.add_argument("--data", required=True)
    parser.add_argument("--task", choices=["vehicle", "obstacle", "layout"], required=True)
    parser.add_argument("--model", help="segはyolo11s-seg.pt、障害物はyolo11n.ptなど")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--name")
    parser.add_argument("--accept-train-only", action="store_true",
                        help="独立した検証なしの試験学習を明示的に許可")
    args = parser.parse_args()
    try:
        opts, has_val = prepare_options(
            args.data, args.task, epochs=args.epochs, imgsz=args.imgsz,
            batch=args.batch, name=args.name,
            accept_train_only=args.accept_train_only)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    model_path = args.model or ("yolo11s-seg.pt" if args.task == "vehicle"
                                else "yolo11n-seg.pt" if args.task == "layout"
                                else "yolo11n.pt")
    if args.task in ("vehicle", "layout"):
        opts.update({"mosaic": 0.25, "mixup": 0., "copy_paste": 0.})
    from ultralytics import YOLO
    model = YOLO(model_path)
    expected = "segment" if args.task in ("vehicle", "layout") else "detect"
    if model.task != expected:
        parser.error(f"{args.task}には{expected}タスクの重みが必要です")
    if args.device == "auto":
        import torch
        opts["device"] = 0 if torch.cuda.is_available() else "cpu"
    else:
        opts["device"] = args.device
    if not has_val:
        print("【注意】同じ撮影データだけの試験学習。精度改善とは判定できません")
    print("【安全】本番のbest.pt / config.json / Supabase / アプリを変更しません")
    model.train(**opts)
    trainer = getattr(model, "trainer", None)
    print("【学習出力先】", getattr(trainer, "save_dir", "(ログを確認)"))
    print("【採用前】別撮影の未使用動画で認識率と駐車枠の誤判定を検証してください")


if __name__ == "__main__":
    main()
