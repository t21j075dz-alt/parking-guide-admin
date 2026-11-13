#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""道の駅日光の動画を駐車枠なしでYOLOプレビューする研究用ツール。

車両・歩行者・自転車・モデルが対応する障害物の検出矩形、信頼度、
追跡IDのみ確認。区画の満空判定、Supabase通信、設定の書換えはしない。
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import time

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
CLASSES_VEHICLE = {"car", "truck", "bus", "van", "vehicle"}
CLASSES_BICYCLE = {"bicycle", "motorcycle", "tricycle", "awning_tricycle"}
CLASSES_PERSON = {"person", "pedestrian", "people"}


def read_model_settings(config_path, explicit_model=""):
    """既存config.jsonは読み取り専用。区画設定と接続情報には触れない。"""
    path = Path(config_path).expanduser()
    data = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("研究用config.jsonはJSONオブジェクトで指定してください")
    elif not explicit_model:
        raise ValueError("config.jsonがありません。学習済みモデルを--modelで指定してください")
    name = explicit_model or data.get("vehicle_model")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("車両YOLOモデルが未指定です。--model で重みファイルを指定してください")
    candidate = Path(name.strip()).expanduser()
    locations = [candidate]
    if not candidate.is_absolute():
        locations.extend((path.parent / candidate, Path(__file__).resolve().parent / candidate))
    result = next((p.resolve() for p in locations if p.is_file()), None)
    if result is None:
        raise ValueError("YOLOモデルが見つかりません: " + name +
                         "。モデルの.ptファイルの保存場所を指定してください")
    obstacle = data.get("obstacle_model") or ""
    obstacle_path = None
    if isinstance(obstacle, str) and obstacle.strip():
        op = Path(obstacle.strip()).expanduser()
        options = [op] if op.is_absolute() else [op, path.parent / op, Path(__file__).resolve().parent / op]
        obstacle_path = next((p.resolve() for p in options if p.is_file()), None)
    confidence = float(data.get("tracking_confidence", 0.15))
    if not 0 < confidence <= 1:
        raise ValueError("tracking_confidenceの範囲は0～1です")
    size = int(data.get("image_size", 960))
    if not 320 <= size <= 2048:
        raise ValueError("image_sizeの範囲は320～2048です")
    return {
        "model": str(result), "obstacle_model": str(obstacle_path) if obstacle_path else None,
        "obstacle_model_unavailable": bool(obstacle and obstacle_path is None),
        "confidence": confidence, "image_size": size,
        "tracker": str(data.get("tracker_file") or "botsort.yaml"),
        "night_vision_mode": str(data.get("night_vision_mode") or "auto"),
    }


def read_segmentation_preview_settings(config_path, model, quality="high", imgsz=0):
    """Use the selected trained instance-segmentation checkpoint without parking zones."""
    from segmentation_quality import resolve_segmentation_settings

    if not isinstance(model, str) or not model.strip():
        raise ValueError("追加学習した車両輪郭モデル（-seg .pt）のパスを指定してください")
    candidate = Path(model.strip()).expanduser()
    if not candidate.is_file():
        raise ValueError("車両輪郭モデルが見つかりません: " + model)
    path = Path(config_path).expanduser()
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    if not isinstance(data, dict):
        raise ValueError("モデル設定ファイルが不正です")
    seg = resolve_segmentation_settings(
        quality.lower(), tracking=True, model=str(candidate.resolve()),
        imgsz=imgsz or None)
    conf = float(data.get("tracking_confidence", .15))
    if not 0 < conf <= 1:
        raise ValueError("追跡信頼度は0から1の範囲です")
    return {
        "model": str(candidate.resolve()), "obstacle_model": None,
        "obstacle_model_unavailable": False, "confidence": conf,
        "image_size": seg.imgsz,
        "tracker": str(data.get("tracker_file") or "botsort.yaml"),
        "night_vision_mode": str(data.get("night_vision_mode") or "auto"),
        "segmentation": seg,
    }


def stabilize_vehicle_ids(matcher, detections, video_seconds, frame):
    """Use the stabilizer's returned records, not the original raw tracker IDs."""
    return matcher.update(detections, video_seconds, frame=frame)


def validate_source(filename):
    path = Path(filename).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("動画が見つからないか未対応の形式です: " + str(path))
    if path.stat().st_size < 1:
        raise ValueError("動画が空です")
    if path.name.startswith("YOLO判定_") or path.name.lower().startswith("yolo_annotated"):
        raise ValueError("判定結果を重ねた動画ではなく、元の撮影映像を選んでください")
    return path


def detection_category(name):
    name = str(name).lower()
    if name in CLASSES_VEHICLE:
        return "vehicles"
    if name in CLASSES_BICYCLE:
        return "bikes"
    if name in CLASSES_PERSON:
        return "people"
    return "obstacles"


def count_frame(vehicles, blockers):
    counts = Counter(detection_category(d.get("name", "")) for d in vehicles + blockers)
    return {key: counts[key] for key in ("vehicles", "bikes", "people", "obstacles")}


def draw_preview(frame, vehicles, blockers, frame_seconds, cycle, cv2):
    """元フレームとは別の描画用コピーに、区画線なしで検知矩形だけ描く。"""
    height, width = frame.shape[:2]
    canvas = cv2.copyMakeBorder(frame.copy(), 0, 82, 0, 0, cv2.BORDER_CONSTANT,
                                value=(22, 27, 32))
    colors = {
        "vehicles": (55, 218, 90), "bikes": (240, 175, 65),
        "people": (65, 210, 240), "obstacles": (95, 105, 240),
    }
    for item in vehicles + blockers:
        box = item.get("display_bbox") or item.get("bbox")
        if not box or len(box) != 4:
            continue
        x1, y1, x2, y2 = (int(v) for v in box)
        x1, y1 = max(0, min(width - 1, x1)), max(0, min(height - 1, y1))
        x2, y2 = max(0, min(width - 1, x2)), max(0, min(height - 1, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        group = detection_category(item.get("name", ""))
        color = colors[group]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        confidence = item.get("confidence", 0)
        track = item.get("track_id")
        label = f"{item.get('name', 'object')} {float(confidence):.2f}"
        if track is not None:
            label += f" ID:{track}"
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, .48, 1)
        top = max(0, y1 - text_h - 8)
        right = min(width - 1, x1 + text_w + 8)
        cv2.rectangle(canvas, (x1, top), (right, top + text_h + 8), color, -1)
        cv2.putText(canvas, label, (x1 + 4, top + text_h + 3),
                    cv2.FONT_HERSHEY_SIMPLEX, .48, (10, 19, 28), 1, cv2.LINE_AA)

    counts = count_frame(vehicles, blockers)
    summary = ("VEHICLES {vehicles} | BIKES {bikes} | PEOPLE {people} | OTHER {obstacles}"
               .format(**counts))
    cv2.putText(canvas, summary, (12, height + 28),
                cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"RECORDING / NOT LIVE | NO PARKING ZONES | "
                f"TIME {frame_seconds:.1f}s | LOOP {cycle}", (12, height + 57),
                cv2.FONT_HERSHEY_SIMPLEX, .52, (205, 210, 220), 1, cv2.LINE_AA)
    return canvas


def run(args):
    try:
        import cv2
        from ultralytics import YOLO
        from monitor import infer_frame, detector_boxes, VEHICLE_NAMES, BLOCKING_NAMES, CLASS_ALIASES
        from segmentation_quality import infer_segments
        from vehicle_segmentation import tracked_segment_detections, draw_vehicle_contours
        from stable_ids import StableIdMatcher
        from night_vision import inference_frame
    except ImportError as exc:
        raise RuntimeError("YOLO/OpenCVが必要です。研究用venvのrequirements.txtを確認してください") from exc

    source = validate_source(args.video)
    settings = (read_segmentation_preview_settings(
        args.config, args.segmentation_model, args.segmentation_quality,
        args.segmentation_imgsz) if args.segmentation_tracking
        else read_model_settings(args.config, args.model))
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise ValueError("動画を開けません。動画形式やアクセス権限を確認してください")

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if not 1 <= fps <= 120:
        capture.release()
        raise ValueError("動画のFPSが取得できません")
    frame_count = 0
    cycle = 1
    per_frame_peaks = Counter()
    processed = 0
    output = None
    writer = None
    try:
        vehicle = YOLO(settings["model"])
        if args.segmentation_tracking and vehicle.task != "segment":
            raise ValueError("選択した重みは輪郭モデルではありません。task=segmentの.ptを選んでください")
        extra = YOLO(settings["obstacle_model"]) if settings["obstacle_model"] else None
        stable_ids = StableIdMatcher(max_missing=12.0) if args.segmentation_tracking else None
        mask_found = 0
        if settings["obstacle_model_unavailable"]:
            print("【注意】障害物モデルの重みが見つかりません。対応する検出のみ表示します。")
        print(f"【元動画】{source} / {fps:.1f} FPS / {total or '?'}フレーム")
        print(f"【使用YOLOモデル】{settings['model']}")
        if args.segmentation_tracking:
            seg = settings["segmentation"]
            print(f"【車両輪郭】追加学習済み -seg／品質 {seg.quality}／"
                  f"解析 {seg.imgsz}px／高精細マスク {seg.retina_masks}")
            print("【追跡】同じ輪郭モデルで検出・マスク・追跡IDを計算し、安定IDを再対応付け")
            print("【注意】車体の見える輪郭であり、タイヤの接地点の実測ではありません。")
        print("【実験】区画なし。検出枠・信頼度・追跡IDを確認します。満空判定はしません。")
        if args.segmentation_tracking:
            supported = {str(value).lower().strip().replace("-", "_")
                         for value in vehicle.names.values()}
            print("【モデルのクラス】" + ", ".join(sorted(supported)))
            if not supported.intersection(CLASSES_PERSON):
                print("【注意】この輪郭モデルに人物クラスがない場合、people=0は人物不在を意味しません。")
            if not supported.intersection({"traffic_cone", "shopping_cart", "cart"}):
                print("【注意】障害物クラスがない場合、obstacles=0は障害物不在を意味しません。")
        if not args.all_frames and not args.save_video:
            print("【解析方法】通常プレビューでは動画の再生時間に合わせてフレームを間引きます。")
            print("【全フレームを確認する方法】起動メニュー4（全フレーム解析＋MP4保存）を選択してください。")
        print("【クラウド】Supabaseへは接続せず、登録済み59区画を変更しません。")
        print("【画面】Q=停止 / SPACE=一時停止 / S=静止画保存 / R=最初から再生")
        if args.save_video:
            target = Path(args.output).expanduser().resolve()
            target.mkdir(parents=True, exist_ok=True)
            output = target / (("nikko_yolo_segments_" if args.segmentation_tracking
                                else "nikko_yolo_detections_") +
                               datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4")
        pause = False
        start_clock = time.monotonic()
        last = None
        while True:
            if not pause:
                # 保存用動画では全フレームを判定して、動画の再生時間を保つ。
                if not args.save_video and not args.all_frames:
                    wanted = int((time.monotonic() - start_clock) * fps)
                    if wanted > frame_count + 1 and (total <= 0 or wanted < total):
                        capture.set(cv2.CAP_PROP_POS_FRAMES, wanted)
                        frame_count = wanted
                ok, frame = capture.read()
                if not ok or frame is None:
                    if not args.loop or args.save_video:
                        break
                    cycle += 1
                    capture.release()
                    capture = cv2.VideoCapture(str(source))
                    if not capture.isOpened():
                        raise ValueError("動画の2周目を開けません")
                    # 周回で前のトラッカーIDを流用しない。
                    vehicle = YOLO(settings["model"])
                    extra = YOLO(settings["obstacle_model"]) if settings["obstacle_model"] else None
                    if args.segmentation_tracking:
                        stable_ids = StableIdMatcher(max_missing=12.0)
                    frame_count = 0
                    start_clock = time.monotonic()
                    continue
                frame_count += 1
                observed_at = (frame_count - 1) / fps
                if args.segmentation_tracking:
                    adjusted, _, _ = inference_frame(
                        frame, mode=settings["night_vision_mode"])
                    result = infer_segments(
                        vehicle, adjusted, settings["segmentation"], tracking=True,
                        tracker_file=settings["tracker"],
                        confidence=min(.10, settings["confidence"]))[0]
                    vehicles = tracked_segment_detections(
                        result, frame.shape, VEHICLE_NAMES, CLASS_ALIASES)
                    # StableIdMatcher returns NEW detection records with their
                    # verified IDs; it does not mutate the originals.
                    vehicles = stabilize_vehicle_ids(
                        stable_ids, vehicles, observed_at, frame)
                    blockers = detector_boxes(
                        result, frame.shape[1], frame.shape[0], BLOCKING_NAMES)
                    mask_found += sum(
                        bool(d.get("segmentation_contour")) for d in vehicles)
                else:
                    vehicles, blockers = infer_frame(
                        vehicle, extra, frame, settings["confidence"],
                        tracker_file=settings["tracker"], image_size=settings["image_size"],
                        occupancy_confidence=settings["confidence"],
                        night_vision_mode=settings["night_vision_mode"],
                    )
                counts = count_frame(vehicles, blockers)
                for key, count in counts.items():
                    per_frame_peaks[key] = max(per_frame_peaks[key], count)
                view_frame = (draw_vehicle_contours(frame, vehicles)
                              if args.segmentation_tracking else frame)
                last = draw_preview(view_frame, vehicles, blockers, observed_at, cycle, cv2)
                processed += 1
                if output is not None:
                    if writer is None:
                        h, w = last.shape[:2]
                        writer = cv2.VideoWriter(str(output),
                            cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
                        if not writer.isOpened():
                            raise ValueError("出力MP4を作成できません")
                    writer.write(last)
                if args.max_frames and processed >= args.max_frames:
                    print("【確認】指定フレームまで解析しました")
                    break

            if last is not None and not args.no_window:
                max_width = min(1400, last.shape[1])
                window_size = (max_width, round(last.shape[0] * max_width / last.shape[1]))
                preview = cv2.resize(last, window_size) if max_width < last.shape[1] else last
                cv2.imshow("Nikko YOLO - detections ONLY (Q quit, SPACE pause, S capture)", preview)
                key = cv2.waitKey(0 if pause else 1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if key == ord(" "):
                    pause = not pause
                    if not pause:
                        # 再開時の経過時間に一時停止時間を含めない。
                        start_clock = time.monotonic() - frame_count / fps
                elif key in (ord("s"), ord("S")):
                    folder = Path(args.output).expanduser().resolve()
                    folder.mkdir(parents=True, exist_ok=True)
                    image_path = folder / ("nikko_detection_snapshot_" +
                                           datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".png")
                    cv2.imwrite(str(image_path), last)
                    print("【保存】"+str(image_path))
                elif key in (ord("r"), ord("R")) and not args.save_video:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    vehicle = YOLO(settings["model"])
                    extra = YOLO(settings["obstacle_model"]) if settings["obstacle_model"] else None
                    if args.segmentation_tracking:
                        stable_ids = StableIdMatcher(max_missing=12.0)
                    frame_count = 0
                    cycle += 1
                    start_clock = time.monotonic()
                    pause = False
            elif not args.save_video and not args.all_frames:
                # GUIなしの状態でもPCに過剰な負荷を掛けず動画の実時間で進める。
                time.sleep(0.005)
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if not args.no_window:
            cv2.destroyAllWindows()

    print(f"【結果】YOLO解析フレーム {processed}／元動画 {total or '?'}フレーム／動画再生周回 {cycle}")
    if total and not args.loop and processed < total and not args.all_frames:
        print("【補足】再生時間に合わせて一部フレームを間引きました。認識漏れとは区別してください。")
    if args.segmentation_tracking:
        print(f"【車両輪郭】マスク輪郭が得られた検出 {mask_found}件（正解率ではありません）")
    print("【検知ピーク（同一フレーム内）】"+
          ", ".join(f"{k}={per_frame_peaks[k]}" for k in
                    ("vehicles","bikes","people","obstacles")))
    print("【重要】検出数は正解率ではありません。実映像と照合してください。")
    if output is not None:
        print("【確認用MP4】"+str(output))
    return processed


def main(argv=None):
    parser = argparse.ArgumentParser(description="日光の録画を駐車枠なしでYOLO検知だけ確認する")
    parser.add_argument("--video", required=True, help="元動画ファイル（Gドライブ等）")
    parser.add_argument("--config", default="config.json", help="モデル設定を読み取るJSON")
    parser.add_argument("--model", default="", help="従来の検出モデル.pt（通常モードのみ）")
    parser.add_argument("--segmentation-tracking", action="store_true",
                        help="駐車枠なしで車両輪郭と追跡IDを同一-segモデルから表示")
    parser.add_argument("--segmentation-model", default="",
                        help="学習済み-seg.ptのフルパス（未指定なら起動しない）")
    parser.add_argument("--segmentation-quality", default="high",
                        choices=("standard","high","maximum"),
                        help="輪郭表示の品質（高精細標準はhigh 960）")
    parser.add_argument("--segmentation-imgsz", type=int, default=0,
                        help="輪郭解析サイズ（0なら品質プリセット値）")
    parser.add_argument("--output", default="reports_nikko_detection_only")
    parser.add_argument("--save-video", action="store_true", help="検出矩形を重ねたMP4を保存")
    parser.add_argument("--all-frames", action="store_true", help="間引かずに全フレーム解析")
    parser.add_argument("--loop", action="store_true", help="停止まで同じ元動画を繰り返す")
    parser.add_argument("--no-window", action="store_true", help="GUI不要の場合")
    parser.add_argument("--max-frames", type=int, default=0, help="先頭から試す解析フレーム数")
    args = parser.parse_args(argv)
    if args.segmentation_tracking and not args.segmentation_model:
        parser.error("車両輪郭モデル（--segmentation-model）を指定してください")
    if args.max_frames < 0:
        parser.error("--max-frames は0以上")
    if args.save_video and args.loop:
        parser.error("無制限に保存しないため --save-video と --loop は併用できません")
    if args.no_window and args.loop and not args.max_frames:
        parser.error("画面なしの無限ループは無効です。--max-framesを指定してください")
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, "【検知プレビュー失敗】"+str(exc)+"\n")


if __name__ == "__main__":
    main()
