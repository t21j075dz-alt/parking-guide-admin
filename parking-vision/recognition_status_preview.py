# -*- coding: utf-8 -*-
"""Preview CURRENT and EXPERIMENTAL YOLO recognition on LOCAL photos or video.

Only reads local models/images; creates a side-by-side JPEG and CSV per sample.
Does not alter config.json, use Supabase, or claim to evaluate accuracy.
A missing model is shown as MISSING, never replaced by a pretrained model.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

TASK_PREFIXES = {
    "vehicle_mask": ("vehicle_lighting_auto", "vehicle_241_pilot",
                     "vehicle_reviewed", "vehicle_242_pilot"),
    "obstacle": ("obstacle_auto", "obstacle_241_pilot", "obstacle_242_pilot"),
    "vehicle_box": ("vehicle_box_auto",),
}


def find_weight(task, root=ROOT):
    """Only existing LOCAL completed weights. No implicit pretrained fallback."""
    folders = root / "runs" / "unified_training"
    choices = []
    if folders.is_dir():
        for folder in folders.iterdir():
            if not folder.is_dir() or not any(
                    folder.name.startswith(prefix) for prefix in TASK_PREFIXES[task]):
                continue
            for name in ("last.pt", "best.pt"):
                file = folder / "weights" / name
                if file.is_file() and file.stat().st_size:
                    choices.append((file.stat().st_mtime, file))
                    break
    if task == "vehicle_mask":
        old = root / "runs" / "vehicle_segmentation"
        if old.is_dir():
            for folder in old.iterdir():
                if not folder.is_dir():
                    continue
                file = folder / "weights" / "last.pt"
                if file.is_file() and file.stat().st_size:
                    choices.append((file.stat().st_mtime, file))
    return max(choices, key=lambda entry: entry[0])[1] if choices else None


def current_weight(root=ROOT):
    config = root / "config.json"
    if not config.is_file():
        return None
    settings = json.loads(config.read_text(encoding="utf-8-sig"))
    value = settings.get("vehicle_model")
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    # Prevent an implicit weights download disguised as the current model.
    return path.resolve() if path.is_file() and path.stat().st_size else None


def spread_indices(count, max_count):
    if count < 1 or max_count < 1:
        return []
    if count <= max_count:
        return list(range(count))
    if max_count == 1:
        return [0]
    return [i * (count - 1) // (max_count - 1) for i in range(max_count)]


def source_photos(path, samples):
    photos = sorted(p for p in path.rglob("*") if p.is_file()
                    and p.suffix.lower() in EXTENSIONS)
    if not photos:
        raise ValueError(f"画像がありません: {path}")
    return [photos[i] for i in spread_indices(len(photos), samples)]


def model_paths(root, overrides):
    found = {"current": current_weight(root)}
    for task in TASK_PREFIXES:
        explicit = overrides.get(task)
        if explicit:
            path = Path(explicit).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"モデルがありません: {path}")
            found[task] = path
        else:
            found[task] = find_weight(task, root)
    return found


def source_from_workspace(root):
    marker = root / "annotation_workspaces" / "photos_242" / "source.json"
    if not marker.is_file():
        raise ValueError("画像フォルダが記録されていません。--images または --video を指定")
    source = json.loads(marker.read_text(encoding="utf-8")).get("images_root")
    if not source or not Path(source).is_dir():
        raise ValueError("以前の画像フォルダが見つかりません。--images を指定してください")
    return Path(source)


def load_frame(path, cv2, np):
    raw = np.fromfile(str(path), dtype=np.uint8)
    frame = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"読み込めない画像: {path}")
    return frame


def panel(frame, text, cv2, np, width=555, height=340):
    h, w = frame.shape[:2]
    scale = min(width / w, (height - 34) / h)
    resized = cv2.resize(frame, (max(1, round(w * scale)),
                                 max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA)
    tile = np.full((height, width, 3), (24, 30, 42), dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = 34 + (height - 34 - resized.shape[0]) // 2
    tile[y:y+resized.shape[0], x:x+resized.shape[1]] = resized
    cv2.putText(tile, text[:65], (12, 24), cv2.FONT_HERSHEY_SIMPLEX,
                .61, (235, 237, 245), 2, cv2.LINE_AA)
    return tile


def infer(model, frame, label, conf, imgsz, cv2, np):
    if model is None:
        missing = np.zeros_like(frame)
        cv2.putText(missing, "NO LOCAL WEIGHTS - NOT TRAINED", (20, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, .65, (60, 210, 245), 2)
        return panel(missing, label + " / NOT FOUND", cv2, np), {
            "status": "missing", "count": None, "masks": None, "classes": "{}"
        }
    result = model.predict(source=frame, conf=conf, imgsz=imgsz,
                           verbose=False)[0]
    image = result.plot()
    boxes = getattr(result, "boxes", None)
    count = len(boxes) if boxes is not None else 0
    masks = getattr(result, "masks", None)
    mask_count = len(masks) if masks is not None else 0
    types = Counter()
    if boxes is not None:
        ids = boxes.cls.detach().cpu().tolist()
        for cls in ids:
            types[str(result.names.get(int(cls), int(cls)))] += 1
    return panel(image, f"{label} / objects={count} masks={mask_count}", cv2, np), {
        "status": "ready", "count": count, "masks": mask_count,
        "classes": json.dumps(types, ensure_ascii=False, sort_keys=True)
    }


def main():
    parser = argparse.ArgumentParser(
        description="現在モデルと自動追加学習モデルの検出結果を画像・動画で比較（読み取り専用）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--images", help="画像の入ったフォルダ。省略時は以前の241枚を使用")
    group.add_argument("--video", help="録画MP4等のフルパス")
    parser.add_argument("--vehicle-mask", help="車体輪郭の比較用重み（.pt）")
    parser.add_argument("--obstacle", help="障害物モデル（.pt）")
    parser.add_argument("--vehicle-box", help="車両検出モデル（.pt）")
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--interval", type=float, default=5.,
                        help="動画を何秒おきにサンプリングするか")
    parser.add_argument("--conf", type=float, default=.35)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--save-only", action="store_true",
                        help="画面を表示せずJPEG・CSVだけ保存")
    parser.add_argument("--status-only", action="store_true",
                        help="ローカルモデルの有無と場所だけ確認（推論しない）")
    args = parser.parse_args()

    try:
        if not 1 <= args.samples <= 100 or args.interval <= 0 or not 0 < args.conf < 1:
            raise ValueError("samples=1～100、interval>0、conf=0～1で指定")
        paths = model_paths(ROOT, {"vehicle_mask": args.vehicle_mask,
                                   "obstacle": args.obstacle,
                                   "vehicle_box": args.vehicle_box})
        print("【現在のモデル状態】")
        for task, path in paths.items():
            print(f"  {task}: {path if path else 'ローカル重みなし（未学習・未配置の可能性）'}")
        if args.status_only:
            return
        import cv2
        import numpy as np
        from ultralytics import YOLO

        chosen = Path(args.video).expanduser().resolve() if args.video else (
            Path(args.images).expanduser().resolve() if args.images else source_from_workspace(ROOT))
        if not chosen.exists():
            raise ValueError(f"入力がありません: {chosen}")

        models = {}
        for task, weight in paths.items():
            if weight is None:
                models[task] = None
                continue
            try:
                models[task] = YOLO(str(weight))
                expected = ("segment" if task == "vehicle_mask" else "detect")
                if models[task].task != expected:
                    print(f"【注意】{task}の重みは{models[task].task}。期待形式={expected}のため除外")
                    models[task] = None
            except Exception as exc:
                print(f"【注意】{task}の重みを読み込めません: {type(exc).__name__}: {exc}")
                models[task] = None
        if not any(models.values()):
            print("【注意】読み込めるモデルがありません。学習が完了した重みを確認してください")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        outdir = ROOT / "runs" / "recognition_status" / stamp
        outdir.mkdir(parents=True, exist_ok=False)
        summary = []
        def display_frame(frame, source_id, index):
            tiles = [panel(frame, "ORIGINAL", cv2, np)]
            row = {"source": source_id}
            for task in ("current", "vehicle_mask", "obstacle", "vehicle_box"):
                tile, detail = infer(models[task], frame, task.upper(),
                                     args.conf, args.imgsz, cv2, np)
                tiles.append(tile)
                for key, value in detail.items():
                    row[task + "_" + key] = value
            # Side-by-side comparison, no changes to the original photo.
            legend = np.full((340, 555, 3), (24, 30, 42), dtype=np.uint8)
            for idx, text in enumerate((
                    "Current = config.json vehicle_model",
                    "Vehicle_mask = fine-tuned segmentation",
                    "Obstacle = fine-tuned obstacle detector",
                    "Vehicle_box = derived bbox detector",
                    "NO LOCAL WEIGHTS = not evaluated",
                    "Labels are predictions, not verified truth",
                    "Press any key for next, Q to quit")):
                cv2.putText(legend, text, (14, 40+idx*39),
                            cv2.FONT_HERSHEY_SIMPLEX, .59,
                            (220, 230, 240), 2, cv2.LINE_AA)
            tiles.append(legend)
            left = np.hstack(tiles[:3])
            right = np.hstack(tiles[3:])
            mosaic = np.vstack([left, right])
            dst = outdir / f"recognition_{index:03d}.jpg"
            ok, encoded = cv2.imencode(".jpg", mosaic)
            if not ok:
                raise ValueError(f"結果画像を保存できません: {dst}")
            encoded.tofile(str(dst))
            row["saved_jpg"] = str(dst)
            summary.append(row)
            print(f"【比較結果】{index+1}: {dst}", flush=True)
            if not args.save_only:
                cv2.namedWindow("YOLO Recognition Comparison", cv2.WINDOW_NORMAL)
                cv2.imshow("YOLO Recognition Comparison", mosaic)
                code = cv2.waitKey(0) & 0xFF
                return code in (ord("q"), ord("Q"), 27)
            return False

        if args.video:
            cap = cv2.VideoCapture(str(chosen))
            if not cap.isOpened():
                raise ValueError(f"録画を開けません: {chosen}")
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if fps <= 0:
                raise ValueError("動画のfpsが取得できません")
            try:
                for index in range(args.samples):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, round(index * args.interval * fps))
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if display_frame(frame, f"{chosen.name}@{index*args.interval:.1f}s", index):
                        break
            finally:
                cap.release()
        else:
            images = source_photos(chosen, args.samples)
            for index, path in enumerate(images):
                frame = load_frame(path, cv2, np)
                if display_frame(frame, str(path), index):
                    break

        if not args.save_only:
            cv2.destroyAllWindows()
        if summary:
            columns = list(summary[0].keys())
            report = outdir / "recognition_counts.csv"
            with report.open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(summary)
            print("【確認画像の保存先】", outdir)
            print("【検出数CSV】", report)
            print("【注意】241枚は学習データのため、正確さの評価には別撮影の映像を使ってください")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
