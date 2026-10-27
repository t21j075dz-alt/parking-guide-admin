#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""駐車区画の写る場所をマウスで登録。専門的な座標入力は不要。"""
import argparse
import json
from pathlib import Path

import cv2
from camera_recording import open_camera


def main():
    parser = argparse.ArgumentParser(description="カメラに写る駐車枠の位置を登録")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--source", help="写真の枠を登録する動画・カメラURL（設定ファイルより優先）")
    args = parser.parse_args()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    source = args.source if args.source is not None else config.get("source", 0)
    if isinstance(source, str) and source.isdecimal():
        source = int(source)
    camera = open_camera(cv2, source, config.get("camera_backend", "auto"))
    ok, frame = camera.read()
    camera.release()
    if not ok:
        raise SystemExit("カメラ画像が取得できません。source を確認してください")
    height, width = frame.shape[:2]
    names = [str(x) for x in config.get("space_uids", [])]
    if not names:
        raise SystemExit("config.json の space_uids に実際の駐車枠IDを入力してください")

    areas = dict(config.get("space_zones") or {})
    mode = 0
    clicked = []
    phase = "spaces"
    print("写真に写る駐車枠の四隅を、時計回りに4回クリックしてください。")
    print("Enter: 次の枠  /  s: 枠を飛ばす  /  e: 入口  /  x: 出口  /  q: 保存して終了")
    print("輪郭は画面で確認し、よく見えない枠は登録しないでください。")

    def current_name():
        return names[mode] if phase == "spaces" and mode < len(names) else phase

    def mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if len(clicked) < 4:
            clicked.append([round(x / width, 5), round(y / height, 5)])

    cv2.namedWindow("Parking: mark four corners")
    cv2.setMouseCallback("Parking: mark four corners", mouse)
    while True:
        view = frame.copy()
        for uid, polygon in areas.items():
            if len(polygon) < 3:
                continue
            pixels = [(round(p[0] * width), round(p[1] * height)) for p in polygon]
            for a, b in zip(pixels, pixels[1:] + pixels[:1]):
                cv2.line(view, a, b, (0, 220, 0), 2)
            cv2.putText(view, uid, pixels[0], cv2.FONT_HERSHEY_SIMPLEX,
                        0.58, (255, 255, 255), 2)
        for point in clicked:
            cv2.circle(view, (round(point[0] * width), round(point[1] * height)), 6, (0, 0, 255), -1)
        cv2.putText(view, f"{current_name()}  {len(clicked)}/4 points", (12, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("Parking: mark four corners", view)
        key = cv2.waitKey(50) & 0xFF
        if len(clicked) == 4:
            areas[current_name()] = clicked[:]
            print(f"登録: {current_name()}")
            clicked.clear()
            if phase == "spaces":
                mode += 1
                if mode >= len(names):
                    phase = "entry_zone"
        if key == ord("q"):
            break
        if key == ord("s"):
            clicked.clear()
            if phase == "spaces":
                mode += 1
                if mode >= len(names):
                    phase = "entry_zone"
            else:
                phase = "exit_zone" if phase == "entry_zone" else "complete"
        if key == ord("e"):
            clicked.clear()
            phase = "entry_zone"
        if key == ord("x"):
            clicked.clear()
            phase = "exit_zone"
        if key == 8:  # Backspaceでクリックを1点取り消す
            if clicked:
                clicked.pop()
        if key == ord("r"):
            clicked.clear()
            areas.pop(current_name(), None)
        if key == 13 and phase == "spaces":  # 任意の枠へ進む
            clicked.clear()
            mode += 1
            if mode >= len(names):
                phase = "entry_zone"

    config["space_zones"] = {uid: polygon for uid, polygon in areas.items() if uid in names}
    for key in ("entry_zone", "exit_zone"):
        if key in areas:
            config[key] = areas[key]
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cv2.destroyAllWindows()
    print(f"{path} に保存しました。登録区画: {len(config['space_zones'])}")


if __name__ == "__main__":
    main()
