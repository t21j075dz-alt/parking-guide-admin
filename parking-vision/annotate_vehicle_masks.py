# -*- coding: utf-8 -*-
"""Local mouse-driven YOLO segmentation annotation. No remote upload.

Usage:
    python annotate_vehicle_masks.py --images-dir "dataset_session_A"

Clicks create a polygon around the VISIBLE vehicle body (not its shadow).
S explicitly saves even an EMPTY label for a frame without target vehicles.
N skips the image and leaves it UNLABELED; the dataset builder then rejects it.
All four supported categories retain their COCO class IDs.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from vehicle_mask_dataset import TARGET_CLASSES, validate_label


def polygon_to_yolo(class_id, points, width, height):
    if class_id not in TARGET_CLASSES:
        raise ValueError("対象外の車両クラスです")
    if width <= 0 or height <= 0 or len(points) < 3:
        raise ValueError("輪郭は最低3点を指定してください")
    coords = []
    for x, y in points:
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("画像の外の点は利用できません")
        coords.extend((x / width, y / height))
    line = f"{class_id} " + " ".join(f"{v:.6f}" for v in coords)
    validate_label(line, "手動で指定した車体")
    return line


def yolo_to_polygon(line, width, height):
    validate_label(line, "既存ラベル")
    values = line.split()
    return int(values[0]), [
        (min(width-1, round(float(values[i]) * width)),
         min(height-1, round(float(values[i+1]) * height)))
        for i in range(1, len(values), 2)
    ]


def annotate_folder(folder):
    import cv2

    folder = Path(folder).resolve()
    images = sorted(p for p in folder.iterdir()
                    if p.is_file() and p.suffix.lower() in
                    {".jpg", ".jpeg", ".png", ".bmp", ".webp"})
    if not images:
        raise ValueError("画像がありません。先にprepare_vehicle_mask_frames.pyを実行してください")
    labels_dir = folder / "labels"
    labels_dir.mkdir(exist_ok=True)
    chosen = 2  # 1=car, 2=motorcycle, 3=bus, 4=truck keys (COCO IDs differ)
    legend = {ord("1"): 2, ord("2"): 3, ord("3"): 5, ord("4"): 7}
    window = "Vehicle polygon annotation (LOCAL)"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    for index, image_file in enumerate(images, 1):
        image = cv2.imread(str(image_file))
        if image is None:
            raise ValueError(f"画像を読み込めません: {image_file}")
        h, w = image.shape[:2]
        scale = min(1., 1280 / max(w, 1), 780 / max(h, 1))
        view_w, view_h = max(1, round(w*scale)), max(1, round(h*scale))
        existing_file = labels_dir / (image_file.stem + ".txt")
        stored = []
        if existing_file.exists():
            stored = [yolo_to_polygon(line, w, h)
                      for line in existing_file.read_text(
                          encoding="utf-8-sig").splitlines() if line.strip()]
        current = []

        def on_mouse(event, x, y, flags, userdata):
            if event == cv2.EVENT_LBUTTONDOWN:
                current.append((max(0, min(w-1, round(x/scale))),
                                max(0, min(h-1, round(y/scale)))))
            elif event == cv2.EVENT_RBUTTONDOWN and current:
                current.pop()

        cv2.resizeWindow(window, view_w, view_h)
        cv2.setMouseCallback(window, on_mouse)
        while True:
            view = image.copy()
            for class_id, polygon in stored:
                if len(polygon) >= 3:
                    import numpy as np
                    vertices = np.asarray(polygon, dtype=np.int32)
                    cv2.polylines(view, [vertices], True, (0,230,255), 2, cv2.LINE_AA)
                    centroid = tuple(vertices.mean(axis=0).astype(int))
                    cv2.putText(view, TARGET_CLASSES[class_id], centroid,
                                cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 2)
            for x, y in current:
                cv2.circle(view, (x,y), 4, (255,0,255), -1)
            if len(current) > 1:
                import numpy as np
                cv2.polylines(view, [np.asarray(current, dtype=np.int32)],
                              False, (255,0,255), 2, cv2.LINE_AA)
            shown = cv2.resize(view, (view_w, view_h))
            cv2.rectangle(shown, (0,0), (view_w, 51), (0,0,0), -1)
            cv2.putText(shown, f"{index}/{len(images)}  class={TARGET_CLASSES[chosen]}  polygons={len(stored)}",
                        (8,19), cv2.FONT_HERSHEY_SIMPLEX, .48,(255,255,255),1)
            cv2.putText(shown, "1 car  2 motorcycle  3 bus  4 truck   ENTER close   U undo   R delete",
                        (8,38), cv2.FONT_HERSHEY_SIMPLEX, .40,(255,255,255),1)
            cv2.imshow(window, shown)
            key = cv2.waitKey(20) & 0xff
            if key == 255:
                continue
            if key in legend:
                chosen = legend[key]
            elif key in (13,10):
                if len(current) < 3:
                    print("【輪郭】最低3点で囲ってEnterを押してください")
                    continue
                try:
                    polygon_to_yolo(chosen, current, w, h)
                except ValueError as exc:
                    print(f"【輪郭を保存できません】{exc}")
                    continue
                stored.append((chosen, current[:]))
                current.clear()
            elif key in (ord("u"), ord("U"), 8):
                if current:
                    current.pop()
            elif key in (ord("r"), ord("R")):
                if current:
                    current.clear()
                elif stored:
                    stored.pop()
            elif key in (ord("s"), ord("S")):
                if current:
                    print("【未確定の点があります】Enterで輪郭を完成するかRで取り消してください")
                    continue
                lines = [polygon_to_yolo(class_id, points, w, h)
                         for class_id, points in stored]
                existing_file.write_text(
                    "\n".join(lines) + ("\n" if lines else ""),
                    encoding="utf-8")
                print(f"【保存】{index}/{len(images)} {image_file.name}: {len(stored)}輪郭")
                break
            elif key in (ord("n"), ord("N")):
                print(f"【保留】{image_file.name}: 未保存の画像はデータセットに入りません")
                break
            elif key in (ord("q"), ord("Q"),27):
                cv2.destroyAllWindows()
                print("【終了】今までSで保存したラベルは維持されています")
                return
    cv2.destroyAllWindows()
    print("【完了】すべての画像を確認しました。未保存がある場合はラベル付けを再開してください")


def main():
    parser = argparse.ArgumentParser(
        description="マウスで車体輪郭を囲み、YOLO-seg正解ラベルをローカル保存")
    parser.add_argument("--images-dir", required=True,
                        help="元動画から切り出した画像のフォルダ")
    args = parser.parse_args()
    if not Path(args.images_dir).is_dir():
        parser.error("画像フォルダが存在しません")
    print("【マウス操作】車体の見えている外周をクリック（影・背景・他車両を含めない）")
    print("【キー】1=乗用車 / 2=二輪車 / 3=バス / 4=トラック、Enter=輪郭確定")
    print("【キー】U=点を戻す / R=点または輪郭を削除 / S=ラベル保存して次へ")
    print("【キー】N=未保存でスキップ / Q=終了。車のない画像は何も囲わずSで空ラベルを保存")
    annotate_folder(args.images_dir)


if __name__ == "__main__":
    main()
