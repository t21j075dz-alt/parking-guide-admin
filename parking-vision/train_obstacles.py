#!/usr/bin/env python3
"""コーン・カートなどの写真を自分でラベル付けした後、追加モデルを学習する。"""
import argparse
from pathlib import Path
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="カラーコーン・カートなどの追加学習")
    parser.add_argument("--data", required=True, help="学習済み画像と正解ラベルをまとめたdata.yaml")
    parser.add_argument("--base", default="yolo11n.pt", help="初期モデル")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--device", default="cpu", help="GPU環境は 0 を指定")
    args = parser.parse_args()
    if not Path(args.data).exists():
        raise SystemExit("data.yaml が見つかりません。写真への正解ラベル登録が先に必要です。")
    model = YOLO(args.base)
    model.train(data=args.data, epochs=args.epochs, imgsz=640,
                batch=8, device=args.device, project="runs/parking-obstacles", name="experiment")
    print("学習済みの重みは runs/parking-obstacles/experiment/weights/best.pt に保存されます。")


if __name__ == "__main__":
    main()
