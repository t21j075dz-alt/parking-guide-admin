"""カメラ画像の上で駐車区画をクリック登録する、日本語の設定画面。"""

import argparse
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

# tkinter はWindowsの標準Pythonに含まれます。
import tkinter as tk
from tkinter import messagebox, ttk


def fetch_spaces(config):
    facility = quote(config["facility_id"], safe="")
    path = (config["supabase_url"].rstrip("/")
            + f"/rest/v1/parking_layouts?facility_id=eq.{facility}&select=layout_data")
    request = Request(path, headers={"apikey": config["publishable_key"]})
    with urlopen(request, timeout=10) as response:
        rows = json.load(response)
    if not rows:
        raise RuntimeError("施設レイアウトがありません。管理アプリで先に保存してください。")
    return [(item["uid"], item.get("name", item["uid"]))
            for item in rows[0]["layout_data"]["objects"]
            if item.get("objectType") == "parkingSpace" and item.get("uid")]


def main():
    parser = argparse.ArgumentParser(description="カメラ上の駐車枠をマウスで登録")
    parser.add_argument("--config", default=str(Path(__file__).with_name("camera-config.json")))
    args = parser.parse_args()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    try:
        import cv2
        from PIL import Image, ImageTk, ImageDraw
    except ImportError as error:
        raise SystemExit("必要なライブラリがありません。pip install -r requirements.txt を実行してください。") from error

    spaces = fetch_spaces(config)
    if not spaces:
        raise SystemExit("この施設に駐車区画がありません。管理画面で区画を追加してください。")

    source = config.get("source", 0)
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    cap = cv2.VideoCapture(source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("カメラ映像を取得できません。camera-config.jsonのsourceを確認してください。")
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    original_width, original_height = image.size
    scale = min(1.0, 1000 / original_width, 640 / original_height)
    image = image.resize((int(original_width * scale), int(original_height * scale)))
    width, height = image.size

    root = tk.Tk()
    root.title("駐車場カメラの区画設定")
    root.geometry(f"{width + 330}x{max(height + 95, 550)}")
    canvas = tk.Canvas(root, width=width, height=height, cursor="crosshair", highlightthickness=1)
    canvas.grid(row=0, column=0, rowspan=3, padx=10, pady=10, sticky="n")
    panel = ttk.Frame(root, padding=12)
    panel.grid(row=0, column=1, sticky="nsew")
    ttk.Label(panel, text="カメラに映る区画を登録", font=("", 12, "bold")).pack(anchor="w")
    ttk.Label(panel, text="① 左の写真で区画の角を順番にクリック\n② 3点以上クリックしたら「保存して次へ」\n③ 映らない区画はスキップ\n※ 車がいない画像で設定してください", justify="left").pack(anchor="w", pady=8)

    candidates = spaces + [("__entry__", "駐車場入口（任意）"), ("__exit__", "駐車場出口（任意）")]
    listing = tk.Listbox(panel, height=min(16, len(candidates)), width=37, exportselection=False)
    listing.pack(fill="x", pady=4)
    for uid, name in candidates:
        listing.insert("end", f"{name}  [{uid}]")
    listing.select_set(0)
    listing.activate(0)
    points = []
    photo = None
    status = tk.StringVar(value="最初の区画を選んで、角をクリックしてください。")
    ttk.Label(panel, textvariable=status, wraplength=295, foreground="#146A47").pack(anchor="w", pady=8)

    def selected():
        return candidates[listing.curselection()[0]][0] if listing.curselection() else None

    def read_polygon(uid):
        if uid == "__entry__":
            return config.get("entry_zone", [])
        if uid == "__exit__":
            return config.get("exit_zone", [])
        return config.setdefault("slots", {}).get(uid, [])

    def redraw():
        nonlocal photo
        displayed = image.copy()
        pen = ImageDraw.Draw(displayed, "RGBA")
        for uid, polygon in config.get("slots", {}).items():
            if uid == selected() or len(polygon) < 3:
                continue
            coords = [(int(x * width), int(y * height)) for x, y in polygon]
            pen.line(coords + [coords[0]], fill=(40, 200, 120, 180), width=3)
        if points:
            coords = [(int(x * width), int(y * height)) for x, y in points]
            if len(coords) >= 2:
                pen.line(coords, fill=(255, 185, 20, 255), width=4)
            if len(coords) >= 3:
                pen.line([coords[-1], coords[0]], fill=(255, 185, 20, 230), width=3)
            for x, y in coords:
                pen.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 185, 20, 255))
        photo = ImageTk.PhotoImage(displayed)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=photo)

    def change_selection(_event=None):
        points.clear()
        uid = selected()
        if uid:
            points.extend([list(p) for p in read_polygon(uid)])
        status.set(f"{uid} の角を登録してください。（現在 {len(points)}点）")
        redraw()

    def click(event):
        points.append([round(max(0, min(1, event.x / width)), 5),
                       round(max(0, min(1, event.y / height)), 5)])
        status.set(f"{selected()}：{len(points)}点指定中。3点以上で保存できます。")
        redraw()

    def save():
        uid = selected()
        if len(points) < 3 or not uid:
            messagebox.showinfo("角が足りません", "区画の角を3点以上クリックしてください。")
            return
        if uid == "__entry__":
            config["entry_zone"] = [p.copy() for p in points]
        elif uid == "__exit__":
            config["exit_zone"] = [p.copy() for p in points]
        else:
            config.setdefault("slots", {})[uid] = [p.copy() for p in points]
        persist()
        status.set(f"{uid} を保存しました。")
        step_next()

    def persist():
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def step_next():
        selection = listing.curselection()
        if selection and selection[0] + 1 < len(candidates):
            listing.selection_clear(0, "end")
            listing.select_set(selection[0] + 1)
            listing.see(selection[0] + 1)
            change_selection()

    def skip():
        status.set("映らない区画は登録されません。")
        step_next()

    def undo():
        if points:
            points.pop()
        redraw()

    def clear():
        points.clear()
        redraw()

    def done():
        persist()
        if not config.get("slots"):
            messagebox.showwarning("未登録", "撮影できる区画を1つ以上登録してください。")
            return
        messagebox.showinfo("保存しました", "区画設定を保存しました。\n次は run.py でカメラ判定を開始できます。")
        root.destroy()

    listing.bind("<<ListboxSelect>>", change_selection)
    canvas.bind("<Button-1>", click)
    for title, action in [("保存して次へ", save), ("この区画は映らない（スキップ）", skip),
                          ("1点戻す", undo), ("この区画を描き直す", clear),
                          ("設定を保存して終了", done)]:
        ttk.Button(panel, text=title, command=action).pack(fill="x", pady=3)
    root.protocol("WM_DELETE_WINDOW", done)
    change_selection()
    root.mainloop()


if __name__ == "__main__":
    main()
