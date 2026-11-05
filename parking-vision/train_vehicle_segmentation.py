# -*- coding: utf-8 -*-
"""Fine-tune an existing YOLO11 segment model on manually labeled video.

Training ONLY: never modifies the parking application's production model,
camera settings, Supabase or GitHub credentials.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def training_kwargs(data, *, epochs=60, imgsz=960, batch=4,
                    device="auto", project="runs/vehicle_segmentation",
                    name="parking_vehicle_masks_v1"):
    data = Path(data).resolve()
    if not data.is_file():
        raise ValueError(f"データセット設定がありません: {data}")
    if not 1 <= int(epochs) <= 1000:
        raise ValueError("epochsは1～1000にしてください")
    if not 256 <= int(imgsz) <= 1920:
        raise ValueError("imgszは256～1920にしてください")
    if not 1 <= int(batch) <= 64:
        raise ValueError("batchは1～64にしてください")
    if not str(name).strip() or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("学習実験名はフォルダ名として指定してください")
    return dict(data=str(data), epochs=int(epochs), imgsz=int(imgsz),
                batch=int(batch), device=(None if device == "auto" else device),
                project=str(project), name=name, workers=0, patience=15,
                exist_ok=False, seed=42, deterministic=True)


def main():
    parser = argparse.ArgumentParser(description="手作業の車体輪郭でYOLO11s-segを追加学習")
    parser.add_argument("--data", required=True, help="作成したdataset.yaml")
    parser.add_argument("--model", default="yolo11s-seg.pt",
                        help="追加学習の元になるsegモデル")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto",
                        help="auto/0/cpu。GPUのないPCではcpuで時間がかかります")
    parser.add_argument("--project", default="runs/vehicle_segmentation")
    parser.add_argument("--name", default="parking_vehicle_masks_v1")
    args = parser.parse_args()
    try:
        options = training_kwargs(args.data, epochs=args.epochs,
                                  imgsz=args.imgsz, batch=args.batch,
                                  device=args.device, project=args.project,
                                  name=args.name)
    except ValueError as exc:
        parser.error(str(exc))
    from ultralytics import YOLO

    model = YOLO(args.model)
    if getattr(model, "task", None) != "segment":
        parser.error("追加学習には-seg.ptなどのsegmentモデルが必要です")
    if options["device"] is None:
        import torch
        options["device"] = 0 if torch.cuda.is_available() else "cpu"
        if options["device"] == "cpu":
            print("【処理負荷】CUDA GPUを利用できません。CPU学習は時間がかかります。")
    print("【追加学習】データは手動の輪郭正解ラベルのみを使用します")
    print("【安全】既存のyolo11s-seg.pt / best.pt、ユーザーアプリ、クラウド設定は上書きしません")
    print("【注意】同じ動画から抜いた近接フレームでの評価は本番性能を示しません")
    model.train(**options)
    best = getattr(getattr(model, "trainer", None), "best", None)
    print(f"【学習完了】best.pt: {best if best else '出力した学習フォルダのweightsを確認してください'}")
    print("【注意】新モデルはまだ実運用へ適用していません。別撮影回のテスト動画で比較してください。")


if __name__ == "__main__":
    main()
