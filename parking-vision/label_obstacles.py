#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""クリック＆ドラッグだけでコーン・カートなどの追加学習データを作る。

例:
 python label_obstacles.py --images "C:\Users\Owner\Desktop\parking-yolo-starter\myparkingphoto_20261022\original"
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import shutil
import sys
import tkinter as tk
from tkinter import ttk, messagebox

CLASSES = ("カラーコーン", "ショッピングカート", "バリケード", "車止め・ポール", "その他の障害物")
CLASS_KEYS = ("traffic_cone", "shopping_cart", "barrier", "bollard", "obstacle")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_SIZE = (1180, 750)


def split_of(file: Path, explicit_val: Path | None = None) -> str:
    """分割の再現性を維持。別日の検証用画像がある場合はそちらを優先する。"""
    if explicit_val is not None:
        return "val" if file.is_relative_to(explicit_val) else "train"
    return "val" if int(hashlib.sha256(file.as_posix().encode("utf-8")).hexdigest()[:8], 16) % 5 == 0 else "train"


def yolo_line(class_id: int, rect: tuple[float, float, float, float]) -> str:
    """画像内の左上(x1,y1)右下(x2,y2)をYOLOの正規化XYWHへ変換。"""
    x1, y1, x2, y2 = rect
    return f"{class_id} {(x1 + x2)/2:.6f} {(y1 + y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}"


def decode_yolo_line(line: str):
    parts = line.strip().split()
    if len(parts) != 5:
        raise ValueError("ラベル形式が違います")
    category = int(parts[0])
    x, y, w, h = (float(part) for part in parts[1:])
    if not (0 <= category < len(CLASSES) and 0 <= x-w/2 <= x+w/2 <= 1
            and 0 <= y-h/2 <= y+h/2 <= 1 and w > 0 and h > 0):
        raise ValueError("ラベル座標が0～1の範囲外です")
    return category, (x-w/2, y-h/2, x+w/2, y+h/2)


def image_path_for(root: Path, file: Path, part: str) -> tuple[Path, Path]:
    # 同名画像の上書きを避け、元画像パスから短いハッシュを作る。
    digest = hashlib.sha256(str(file.resolve()).encode("utf-8")).hexdigest()[:10]
    name = f"{file.stem}_{digest}"
    return root / "images" / part / (name + file.suffix.lower()), root / "labels" / part / (name + ".txt")


class LabelWindow:
    def __init__(self, image_paths: list[Path], dataset: Path, validation_dir: Path | None):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise SystemExit("OpenCVを導入してください: pip install -r requirements.txt") from exc
        self.cv2, self.np = cv2, np
        self.paths, self.dataset, self.validation_dir = image_paths, dataset, validation_dir
        self.index = 0
        self.objects = []
        self.photo = None
        self.drag_start = None
        self.image = None
        self.scale = 1.
        self.width = self.height = 0
        self.root = tk.Tk()
        self.root.title("卒業研究：コーン・カートの写真に正解をつける")
        self.root.minsize(720, 530)
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="① 写っている物の種類を選ぶ → ② 写真上で四角を描く → ③ 次へ").pack(anchor="w")
        self.category = tk.IntVar(value=0)
        buttons = ttk.Frame(toolbar)
        buttons.pack(fill="x", pady=5)
        for no, label in enumerate(CLASSES):
            ttk.Radiobutton(buttons, text=f"{no+1}. {label}", variable=self.category, value=no).pack(side="left", padx=5)
        self.info = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.info).pack(anchor="w")
        self.canvas = tk.Canvas(self.root, background="#172333", cursor="crosshair")
        self.canvas.pack(expand=True, fill="both", padx=8)
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        foot = ttk.Frame(self.root, padding=8)
        foot.pack(fill="x")
        ttk.Button(foot, text="← 前の写真", command=self.previous).pack(side="left", padx=4)
        ttk.Button(foot, text="描いた枠を1つ取り消す", command=self.undo).pack(side="left", padx=4)
        ttk.Button(foot, text="この写真を飛ばす", command=self.skip).pack(side="left", padx=4)
        ttk.Button(foot, text="確認して次の写真 →", command=self.next).pack(side="left", padx=4)
        ttk.Button(foot, text="保存して終了", command=self.finish).pack(side="right", padx=4)
        self.root.bind("<Key-1>", lambda _: self.category.set(0))
        self.root.bind("<Key-2>", lambda _: self.category.set(1))
        self.root.bind("<Key-3>", lambda _: self.category.set(2))
        self.root.bind("<Key-4>", lambda _: self.category.set(3))
        self.root.bind("<Key-5>", lambda _: self.category.set(4))
        self.root.protocol("WM_DELETE_WINDOW", self.finish)
        self.root.after(100, self.load)
        self.root.mainloop()

    def key_paths(self):
        path = self.paths[self.index]
        split = split_of(path, self.validation_dir)
        return image_path_for(self.dataset, path, split)

    def load(self):
        if self.index >= len(self.paths):
            self.finish()
            return
        file = self.paths[self.index]
        # cv2.imreadが日本語名で失敗するWindows環境を考慮。
        array = self.np.fromfile(str(file), dtype=self.np.uint8)
        image = self.cv2.imdecode(array, self.cv2.IMREAD_COLOR)
        if image is None:
            messagebox.showwarning("読み取り失敗", "写真を開けません:\n" + str(file))
            self.index += 1
            self.load()
            return
        self.image = image
        self.height, self.width = image.shape[:2]
        self.scale = min(MAX_SIZE[0]/self.width, MAX_SIZE[1]/self.height, 1.)
        w = max(1, round(self.width * self.scale))
        h = max(1, round(self.height * self.scale))
        resized = self.cv2.resize(image, (w, h), interpolation=self.cv2.INTER_AREA)
        ok, png = self.cv2.imencode(".png", resized)
        if not ok:
            raise ValueError("写真の表示用画像を作れません")
        self.photo = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
        _, label = self.key_paths()
        self.objects = []
        if label.exists():
            for line in label.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        self.objects.append(decode_yolo_line(line))
                    except ValueError:
                        messagebox.showwarning("ラベルを確認", "過去の正解枠に誤りがあります:\n" + str(label))
        self.canvas.configure(width=w, height=h)
        self.update_view()

    def update_view(self):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        for category, (x1, y1, x2, y2) in self.objects:
            self.canvas.create_rectangle(x1*self.width*self.scale, y1*self.height*self.scale,
                                         x2*self.width*self.scale, y2*self.height*self.scale,
                                         outline="#ffdf4d", width=3)
            self.canvas.create_text(x1*self.width*self.scale + 3, y1*self.height*self.scale + 3,
                                    anchor="nw", fill="#fff", text=CLASSES[category],
                                    font=("Yu Gothic UI", 12, "bold"))
        current = self.paths[self.index]
        split = split_of(current, self.validation_dir)
        self.info.set(f"{self.index+1} / {len(self.paths)} 枚｜{current.name}｜"
                      f"正解枠 {len(self.objects)} 件｜保存先：{'検証用' if split=='val' else '学習用'}")
        if self.drag_start:
            self.canvas.create_text(8, 8, anchor="nw", text="ドラッグで四角を描いています",
                                    fill="#fff")

    def clip(self, event):
        return max(0, min(1, event.x / (self.width*self.scale))), \
               max(0, min(1, event.y / (self.height*self.scale)))

    def mouse_down(self, event):
        self.drag_start = self.clip(event)

    def mouse_move(self, event):
        if self.drag_start:
            self.update_view()
            x1, y1 = self.drag_start
            x2, y2 = self.clip(event)
            self.canvas.create_rectangle(
                x1*self.width*self.scale, y1*self.height*self.scale,
                x2*self.width*self.scale, y2*self.height*self.scale,
                outline="#f92b62", width=3, dash=(5, 3))

    def mouse_up(self, event):
        if self.drag_start:
            x1, y1 = self.drag_start
            x2, y2 = self.clip(event)
            a, b, c, d = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            if (c-a)*self.width >= 6 and (d-b)*self.height >= 6:
                self.objects.append((self.category.get(), (a, b, c, d)))
            self.drag_start = None
            self.update_view()

    def save(self):
        target, label = self.key_paths()
        target.parent.mkdir(parents=True, exist_ok=True)
        label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.paths[self.index], target)
        label.write_text("".join(yolo_line(cat, rect) + "\n" for cat, rect in self.objects),
                         encoding="utf-8")

    def undo(self):
        if self.objects:
            self.objects.pop()
            self.update_view()

    def next(self):
        self.save()  # 障害物が一つもないことを確認した写真も負例として保存する
        self.index += 1
        self.load()

    def previous(self):
        if self.index > 0:
            self.save()
            self.index -= 1
            self.load()

    def skip(self):
        # 未確認の画像はデータセットに入れない（誤った空き画像の学習を防ぐ）
        self.index += 1
        self.load()

    def finish(self):
        if self.index < len(self.paths):
            # 今表示中の写真は「次へ」したときだけ保存する。途中の変更は破棄。
            pass
        self.root.destroy()


def find_images(directory: Path, output: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError("写真フォルダが見つかりません: " + str(directory))
    return sorted(p for p in directory.rglob("*") if p.is_file()
                  and p.suffix.lower() in EXTENSIONS
                  and not p.is_relative_to(output))


def write_yaml(output: Path):
    lines = ["# 卒業研究の画像分類。画像・ラベルを別途確認してください。",
             "path: " + json_quote(output.resolve().as_posix()),
             "train: images/train",
             "val: images/val",
             "names:"]
    for i, label in enumerate(CLASS_KEYS):
        lines.append(f"  {i}: {label}")
    (output / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def json_quote(text: str) -> str:
    import json
    return json.dumps(text, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="正解枠をマウスで描き、YOLO学習用データにする")
    parser.add_argument("--images", required=True, help="撮影した写真を入れたフォルダ")
    parser.add_argument("--validation-images", help="別の日・別の場所で撮影した検証用写真フォルダ（推奨）")
    parser.add_argument("--dataset", default="dataset", help="データセット出力先")
    args = parser.parse_args()
    try:
        train_dir = Path(args.images).expanduser().resolve()
        val_dir = Path(args.validation_images).expanduser().resolve() if args.validation_images else None
        dataset = Path(args.dataset).expanduser().resolve()
        images = find_images(train_dir, dataset)
        if val_dir:
            images += [p for p in find_images(val_dir, dataset) if p not in images]
        if not images:
            raise ValueError("jpg・jpeg・pngなどの画像がありません")
        dataset.mkdir(parents=True, exist_ok=True)
        write_yaml(dataset)
        if not val_dir:
            print("注意：検証画像は自動で約20%を分けます。")
            print("同じ連写・同じ駐車場ばかりだと検証スコアが高めに出ます。")
            print("別の日や別の場所の写真があれば --validation-images を使ってください。")
        LabelWindow(images, dataset, val_dir)
        print("保存先:", dataset)
        print("学習する前に学習用/検証用の各クラスに正解枠があるか確認してください。")
    except (OSError, ValueError) as exc:
        sys.exit("写真の登録に失敗しました: " + str(exc))


if __name__ == "__main__":
    main()
