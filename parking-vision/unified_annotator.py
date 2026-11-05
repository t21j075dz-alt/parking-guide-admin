# -*- coding: utf-8 -*-
"""One Tkinter screen to review vehicle polygons and obstacle bounding boxes.

Usage:
  python unified_annotator.py --images "G:\\photos\\original" --workspace "annotation_workspaces/photos_242"
  python unified_annotator.py export --mode vehicle --train-images ... --train-workspace ... --output ... --train-only
Existing YOLO inference boxes are NEVER auto-imported as checked labels.
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from annotate_vehicle_masks import polygon_to_yolo, yolo_to_polygon
from label_obstacles import decode_yolo_line, yolo_line
from unified_annotation_dataset import (
    AnnotationWorkspace, OBSTACLE_CLASSES, VEHICLE_CLASSES, export_cli,
)

MAX_PREVIEW = (1180, 760)


class UnifiedAnnotator:
    def __init__(self, workspace, start_mode="vehicle"):
        import tkinter as tk
        from tkinter import ttk
        import cv2
        import numpy as np

        self.tk, self.ttk, self.cv2, self.np = tk, ttk, cv2, np
        self.workspace = workspace
        self.index = workspace.next_unreviewed() or 0
        self.mode = tk.StringVar(value=start_mode)
        self.active_mode = start_mode
        self.class_id = tk.IntVar(value=2 if start_mode == "vehicle" else 0)
        self.dirty = False
        self.pending = []
        self.drag_start = None
        self.drag_current = None
        self.objects = []
        self.photo = None
        self.image = None
        self.scale = 1.
        self.root = tk.Tk()
        self.root.title("駐車場YOLO｜車両・障害物 ラベル登録")
        self.root.geometry("1270x930")
        self.root.minsize(780, 600)

        head = ttk.Frame(self.root, padding=(10, 8))
        head.pack(fill="x")
        ttk.Label(head, text="車両の輪郭・障害物を1画面で登録",
                  font=("Yu Gothic UI", 15, "bold")).pack(anchor="w")
        self.progress = tk.StringVar()
        ttk.Label(head, textvariable=self.progress, font=("Yu Gothic UI", 10)).pack(anchor="w")
        mode_row = ttk.Frame(head)
        mode_row.pack(fill="x", pady=(6, 4))
        ttk.Label(mode_row, text="登録するもの：").pack(side="left")
        ttk.Radiobutton(mode_row, text="車両（輪郭をクリック）",
                        variable=self.mode, value="vehicle",
                        command=self.change_mode).pack(side="left", padx=7)
        ttk.Radiobutton(mode_row, text="コーン・障害物（ドラッグ）",
                        variable=self.mode, value="obstacle",
                        command=self.change_mode).pack(side="left", padx=7)
        self.classes_frame = ttk.Frame(head)
        self.classes_frame.pack(fill="x", pady=5)
        self.hint = tk.StringVar()
        ttk.Label(head, textvariable=self.hint, wraplength=1220).pack(anchor="w")

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        self.canvas = tk.Canvas(body, bg="#1d2734", highlightthickness=0,
                                cursor="crosshair")
        vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-3>", lambda _: self.undo())

        foot = ttk.Frame(self.root, padding=(10, 7))
        foot.pack(fill="x")
        ttk.Button(foot, text="← 前の画像", command=lambda: self.move(-1)).pack(side="left", padx=3)
        ttk.Button(foot, text="点・枠を戻す", command=self.undo).pack(side="left", padx=3)
        ttk.Button(foot, text="輪郭を確定（Enter）", command=self.finish_polygon).pack(side="left", padx=3)
        ttk.Button(foot, text="対象なしとして保存", command=lambda: self.save(empty=True)).pack(side="left", padx=3)
        ttk.Button(foot, text="確認して保存", command=self.save).pack(side="left", padx=3)
        ttk.Button(foot, text="次の画像（未登録は保留）→",
                   command=lambda: self.move(1)).pack(side="left", padx=3)
        ttk.Button(foot, text="拡大 +", command=lambda: self.zoom(1.4)).pack(side="right", padx=3)
        ttk.Button(foot, text="縮小 −", command=lambda: self.zoom(1/1.4)).pack(side="right", padx=3)
        self.root.bind("<Return>", lambda _: self.finish_polygon())
        self.root.bind("<Control-s>", lambda _: self.save())
        self.root.bind("<Control-z>", lambda _: self.undo())
        self.root.bind("<Escape>", lambda _: self.cancel_pending())
        self.root.bind("<KeyPress>", self.numeric_shortcut)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.build_classes()
        self.load()
        self.root.mainloop()

    def classes(self):
        return VEHICLE_CLASSES if self.mode.get() == "vehicle" else OBSTACLE_CLASSES

    def build_classes(self):
        for child in self.classes_frame.winfo_children():
            child.destroy()
        allowed = self.classes()
        if self.class_id.get() not in allowed:
            self.class_id.set(next(iter(allowed)))
        for i, (class_id, label) in enumerate(allowed.items(), 1):
            self.ttk.Radiobutton(self.classes_frame,
                                 text=f"{i}. {label}",
                                 variable=self.class_id, value=class_id
                                 ).pack(side="left", padx=7)
        self.hint.set(
            "車両：輪郭に沿って左クリック → Enterで1台確定。車が複数なら全台を登録。"
            if self.mode.get() == "vehicle" else
            "障害物：種類を選び、対象をドラッグで四角く囲みます。複数個登録できます。"
        )

    def numeric_shortcut(self, event):
        if event.state & 0x4 or event.keysym not in "12345" or len(event.keysym) != 1:
            return
        choice = list(self.classes())
        key = int(event.keysym) - 1
        if key < len(choice):
            self.class_id.set(choice[key])

    def load(self):
        p = self.workspace.photos[self.index]
        image_bytes = self.np.fromfile(str(p["path"]), dtype=self.np.uint8)
        self.image = self.cv2.imdecode(image_bytes, self.cv2.IMREAD_COLOR)
        if self.image is None:
            raise ValueError(f"写真を開けません: {p['path']}")
        self.height, self.width = self.image.shape[:2]
        self.scale = min(1.0, MAX_PREVIEW[0] / self.width,
                         MAX_PREVIEW[1] / self.height)
        self.read_current()
        self.refresh_photo()

    def read_current(self):
        p = self.workspace.photos[self.index]
        text, reviewed = self.workspace.read(p, self.mode.get())
        self.objects = []
        if self.mode.get() == "vehicle":
            self.objects = [yolo_to_polygon(line, self.width, self.height)
                            for line in text.splitlines() if line.strip()]
            if not reviewed:
                # Explicitly import ONLY previously HAND-reviewed polygons from
                # our own source-video session, never model-generated detections.
                manifest = self.workspace.images_root / "annotation_manifest.csv"
                old = self.workspace.images_root / "labels" / (p["path"].stem + ".txt")
                if manifest.is_file() and old.is_file():
                    from vehicle_mask_dataset import validate_label
                    content = old.read_text(encoding="utf-8-sig")
                    validate_label(content)
                    self.objects = [yolo_to_polygon(line, self.width, self.height)
                                    for line in content.splitlines() if line.strip()]
                    # NOT marked reviewed until person explicitly presses Save.
        else:
            self.objects = [decode_yolo_line(line)
                            for line in text.splitlines() if line.strip()]
        self.pending = []
        self.drag_start = None
        self.drag_current = None
        self.dirty = False
        self.refresh_status()

    def refresh_status(self):
        counts = self.workspace.progress()
        p = self.workspace.photos[self.index]
        state = ("確認済" if self.workspace.is_reviewed(p, self.mode.get())
                 and not self.dirty else "未確定")
        self.progress.set(
            f"{self.index + 1} / {len(self.workspace.photos)}枚　"
            f"車両登録済 {counts['vehicle']}枚　"
            f"障害物登録済 {counts['obstacle']}枚　"
            f"現在：{p['relative']}　{state}（{len(self.objects)}件）")

    def refresh_photo(self):
        w = max(1, round(self.width * self.scale))
        h = max(1, round(self.height * self.scale))
        method = self.cv2.INTER_AREA if self.scale < 1 else self.cv2.INTER_LINEAR
        resized = self.cv2.resize(self.image, (w, h), interpolation=method)
        ok, encoded = self.cv2.imencode(".png", resized)
        if not ok:
            raise ValueError("画像表示用PNGを作成できません")
        self.photo = self.tk.PhotoImage(data=base64.b64encode(encoded.tobytes()).decode("ascii"))
        self.canvas.config(scrollregion=(0, 0, w, h))
        self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self.photo, anchor="nw")
        if self.mode.get() == "vehicle":
            for cls, points in self.objects:
                xy = [coord * self.scale for point in points for coord in point]
                if len(xy) >= 6:
                    c.create_polygon(*xy, outline="#ffd166",
                                     fill="", width=3)
                    c.create_text(xy[0] + 3, xy[1] - 3,
                                  text=VEHICLE_CLASSES[cls], anchor="sw",
                                  fill="white", font=("Yu Gothic UI", 10, "bold"))
            pts = [v * self.scale for point in self.pending for v in point]
            if len(pts) >= 4:
                c.create_line(*pts, fill="#ff4bc2", width=3)
            for x, y in self.pending:
                x, y = x * self.scale, y * self.scale
                c.create_oval(x-4, y-4, x+4, y+4, fill="#ff4bc2", outline="")
        else:
            for cls, (x1, y1, x2, y2) in self.objects:
                xy = (x1*self.width*self.scale, y1*self.height*self.scale,
                      x2*self.width*self.scale, y2*self.height*self.scale)
                c.create_rectangle(*xy, outline="#ffdd63", width=3)
                c.create_text(xy[0]+3, xy[1]+3, anchor="nw",
                              text=OBSTACLE_CLASSES[cls], fill="white",
                              font=("Yu Gothic UI", 10, "bold"))
            if self.drag_start is not None and self.drag_current is not None:
                c.create_rectangle(*(p * self.scale for p in (
                    self.drag_start[0], self.drag_start[1],
                    self.drag_current[0], self.drag_current[1])),
                    outline="#ff4bc2", width=3, dash=(6, 4))

    def point(self, event):
        x = round(self.canvas.canvasx(event.x) / self.scale)
        y = round(self.canvas.canvasy(event.y) / self.scale)
        return max(0, min(x, self.width - 1)), max(0, min(y, self.height - 1))

    def on_mouse_down(self, event):
        point = self.point(event)
        if self.mode.get() == "vehicle":
            self.pending.append(point)
            self.dirty = True
            self.draw()
        else:
            self.drag_start = point
            self.drag_current = point

    def on_mouse_move(self, event):
        if self.mode.get() == "obstacle" and self.drag_start is not None:
            self.drag_current = self.point(event)
            self.draw()

    def on_mouse_up(self, event):
        if self.mode.get() != "obstacle" or self.drag_start is None:
            return
        a, b = self.drag_start, self.point(event)
        x1, x2 = sorted((a[0], b[0]))
        y1, y2 = sorted((a[1], b[1]))
        self.drag_start = self.drag_current = None
        if x2 - x1 >= 6 and y2 - y1 >= 6:
            self.objects.append(
                (self.class_id.get(), (x1/self.width, y1/self.height,
                                       x2/self.width, y2/self.height)))
            self.dirty = True
            self.refresh_status()
        self.draw()

    def finish_polygon(self):
        if self.mode.get() != "vehicle":
            return
        from tkinter import messagebox
        if not self.pending:
            return
        try:
            polygon_to_yolo(self.class_id.get(), self.pending,
                            self.width, self.height)
        except ValueError as exc:
            messagebox.showerror("輪郭を確認", str(exc))
            return
        self.objects.append((self.class_id.get(), self.pending[:]))
        self.pending.clear()
        self.dirty = True
        self.refresh_status()
        self.draw()

    def cancel_pending(self):
        self.pending = []
        self.drag_start = self.drag_current = None
        self.draw()

    def undo(self):
        if self.mode.get() == "vehicle" and self.pending:
            self.pending.pop()
        elif self.objects:
            self.objects.pop()
        else:
            return
        self.dirty = True
        self.refresh_status()
        self.draw()

    def change_mode(self):
        from tkinter import messagebox
        new_mode = self.mode.get()
        old_mode = getattr(self, "active_mode", None)
        if old_mode and new_mode != old_mode and self.dirty:
            if not messagebox.askyesno("未保存の変更",
                                       "現在の登録をまだ保存していません。変更を破棄して切り替えますか？"):
                self.mode.set(old_mode)
                return
        self.active_mode = new_mode
        self.build_classes()
        if self.image is not None:
            self.read_current()
            self.draw()

    def save(self, empty=False):
        from tkinter import messagebox
        if self.pending:
            messagebox.showwarning("未確定の輪郭",
                                   "Enterで車体輪郭を確定するか、Escで取り消してください")
            return
        if empty:
            if self.objects and not messagebox.askyesno(
                    "登録済みの対象を消去",
                    "この種類の対象をすべて削除し、対象なしと記録しますか？"):
                return
            self.objects.clear()
        elif not self.objects:
            if not messagebox.askyesno(
                    "対象なしを確認", "本当にこの画像に対象が一つもありませんか？"
                    "対象外の種類を確認した場合だけ空ラベルで保存します。"):
                return
        if self.mode.get() == "vehicle":
            lines = [polygon_to_yolo(cls, pts, self.width, self.height)
                     for cls, pts in self.objects]
        else:
            lines = [yolo_line(cls, rect) for cls, rect in self.objects]
        photo = self.workspace.photos[self.index]
        self.workspace.save(photo, self.mode.get(),
                            "\n".join(lines) + ("\n" if lines else ""))
        self.dirty = False
        other = "obstacle" if self.mode.get() == "vehicle" else "vehicle"
        if not self.workspace.is_reviewed(photo, other):
            self.mode.set(other)
            self.change_mode()
        else:
            next_index = self.workspace.next_unreviewed(self.index + 1)
            if next_index is None:
                messagebox.showinfo("登録完了",
                                    "すべての写真を両方の種類で確認しました。"
                                    "別撮影の検証データも用意してから学習してください。")
                self.refresh_status()
            else:
                self.index = next_index
                self.load()

    def move(self, delta):
        from tkinter import messagebox
        if self.dirty and not messagebox.askyesno(
                "未保存の変更", "未保存の点や枠があります。破棄して移動しますか？"):
            return
        target = self.index + delta
        if not 0 <= target < len(self.workspace.photos):
            return
        self.index = target
        self.load()

    def zoom(self, factor):
        self.scale = min(1.5, max(0.1, self.scale * factor))
        self.refresh_photo()

    def close(self):
        from tkinter import messagebox
        if self.dirty and not messagebox.askyesno(
                "未保存の変更", "未保存の変更は破棄されます。終了しますか？"):
            return
        self.root.destroy()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export":
        return export_cli(argv[1:])
    parser = argparse.ArgumentParser(
        description="車両の輪郭とコーン等の障害物を同じ画面で登録（教師データ形式は別）")
    parser.add_argument("--images", help="242枚などの元画像フォルダ。省略すると選択画面を開く")
    parser.add_argument("--workspace", default="annotation_workspaces/photos_242",
                        help="登録結果を保存する別フォルダ。再開時も同じ場所")
    parser.add_argument("--start-mode", choices=("vehicle", "obstacle"),
                        default="vehicle")
    args = parser.parse_args(argv)
    if not args.images:
        from tkinter import Tk, filedialog
        chooser = Tk()
        chooser.withdraw()
        args.images = filedialog.askdirectory(
            parent=chooser, title="車両・障害物を登録する写真フォルダを選択")
        chooser.destroy()
        if not args.images:
            print("写真フォルダの選択をキャンセルしました")
            return
    try:
        ws = AnnotationWorkspace(args.images, args.workspace)
        print(f"【写真一覧】{len(ws.photos)}枚を確認。元写真は変更しません")
        print("【安全】車体は輪郭ポリゴン／障害物は四角枠。正解形式は別に保存")
        print("【再開】保存済み画像は保持され、未登録画像から続けます")
        UnifiedAnnotator(ws, start_mode=args.start_mode)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
