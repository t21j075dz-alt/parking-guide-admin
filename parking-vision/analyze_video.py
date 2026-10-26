#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""録画した駐車場動画を安全に分析する（Supabaseには一切通信しない）。

出力:
  駐車枠の状態.csv       動画内の時刻と区画状態
  車両の行動記録.csv     車両ごとの状態遷移と動画内の時刻
  分析結果.json         動画情報と検出件数（正解率ではない）
使用例:
  python analyze_video.py --video "C:\parking\test_house1.mp4" --config config.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import json
from pathlib import Path
import sys

from monitor import (
    SpaceObserver, VehicleTracker, STATUS_NAMES,
    classify_spaces, infer_frame, load_config, overlay, space_for,
)
from stable_ids import StableIdMatcher


PHASE_NAMES = {
    "entering": "入場確認中", "moving": "移動中", "parked": "駐車中",
    "exiting": "出庫中", "exited": "退出済み", "lost": "追跡できなくなった",
}
VIDEO_FORMATS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def video_timestamp(cap, frame_number: int, fps: float, last_timestamp: float) -> float:
    """動画の時刻を優先する。動画情報が欠損している場合はフレーム番号から推定。"""
    import cv2
    decoded = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
    frame_time = max(0.0, (frame_number - 1) / fps)
    if decoded > last_timestamp and decoded > 0:
        return decoded
    # 一部のMP4はPOS_MSECが0/固定となるため、フレーム番号へ戻す
    return max(last_timestamp, frame_time)


def summarize_observations(status_counts: dict, processed_frames: int) -> dict:
    """割合は正解率ではなく「各判定が表示されたフレームの比率」だけ。"""
    if processed_frames <= 0:
        return {}
    return {
        uid: {
            label: {
                "frames": int(counter.get(label, 0)),
                "share_percent": round(counter.get(label, 0) / processed_frames * 100, 2),
            } for label in ("available", "occupied", "blocked", "unknown")
        } for uid, counter in status_counts.items()
    }


def analyze(args) -> Path:
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Pythonの準備が必要です。pip install -r requirements.txt を実行してください") from exc

    video = Path(args.video).expanduser().resolve()
    if not video.is_file() or video.suffix.lower() not in VIDEO_FORMATS:
        raise ValueError("動画ファイルが見つからないか、形式に対応していません（mp4/mov/avi/mkv/webm）")
    config = load_config(args.config)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("動画が開けません。ファイル名・形式・読み取り権限を確認してください")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 0 < fps <= 240:
        cap.release()
        raise ValueError("動画のフレームレートを読み取れません。mp4などに変換してください")
    total_frames = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    run_dir = Path(args.output).expanduser().resolve() / (
        video.stem + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    state_path = run_dir / "駐車枠の状態.csv"
    event_path = run_dir / "車両の行動記録.csv"
    mapping_path = run_dir / "車両ID対応.csv"
    summary_path = run_dir / "分析結果.json"
    zones = config["space_zones"]
    space_states = SpaceObserver(
        zones,
        allow_initial_empty=bool(config.get("allow_unverified_initial_empty", False)),
        absence_hold_seconds=float(config.get("occupied_hold_seconds", 8)),
    )
    tracker = VehicleTracker(config["facility_id"], config["camera_id"],
                             float(config.get("park_seconds", 5)),
                             lost_seconds=float(config.get("reid_window_seconds", 12)))
    stable_ids = StableIdMatcher(max_missing=float(config.get('reid_window_seconds', 12)))
    raw_identity_changes = []
    counts = {uid: Counter() for uid in zones}
    events_by_phase = Counter()
    tracker_sessions = set()
    observation_log = {}
    video_writer = None
    frames = 0
    now = 0.0
    previous_now = -1.0
    last_logged = -1.0
    last_statuses = {}
    raw_track_ids = set()
    prevented_false_free_frames = 0
    id_links_logged = set()
    parked_since = {}
    durations = []
    print("録画を分析します。クラウドへの書き込みは行いません。")
    print("動画:", video)
    print("登録済みの駐車区画:", len(zones))
    try:
        vehicle_model = YOLO(config.get("vehicle_model", "yolo11n.pt"))
        obstacle_path = config.get("obstacle_model")
        obstacle_model = YOLO(obstacle_path) if obstacle_path else None
        confidence = float(config.get("confidence", 0.35))
        tracking_confidence = float(config.get("tracking_confidence", 0.15))
        tracker_file = str(config.get("tracker_file", "botsort.yaml"))
        image_size = int(config.get("image_size", 960))
        with state_path.open("w", encoding="utf-8-sig", newline="") as status_stream, \
             event_path.open("w", encoding="utf-8-sig", newline="") as event_stream, \
             mapping_path.open("w", encoding="utf-8-sig", newline="") as mapping_stream:
            state_csv = csv.writer(status_stream)
            event_csv = csv.writer(event_stream)
            mapping_csv = csv.writer(mapping_stream)
            mapping_csv.writerow(["動画の時刻(秒)", "安定車両ID", "YOLO元ID", "クラス", "検出信頼度"])
            state_csv.writerow(["動画の時刻(秒)", "駐車枠ID", "判定", "判定コード", "車両検知数", "障害物検知数"])
            event_csv.writerow(["動画の時刻(秒)", "追跡セッションID", "カメラ内番号", "状態", "状態コード", "駐車枠ID", "駐車時間(秒・確定分のみ)"])
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames += 1
                now = video_timestamp(cap, frames, fps, previous_now)
                previous_now = now
                vehicles, blockers = infer_frame(
                    vehicle_model, obstacle_model, frame, tracking_confidence,
                    tracker_file=tracker_file, image_size=image_size,
                    occupancy_confidence=confidence,
                )
                vehicles = stable_ids.update(vehicles, now, frame=frame)
                for detection in vehicles:
                    raw = detection.get("raw_track_id")
                    stable = detection.get("track_id")
                    if raw is None or stable is None:
                        continue
                    raw_track_ids.add(raw)
                    change = (stable, raw)
                    if change in id_links_logged:
                        continue
                    id_links_logged.add(change)
                    mapping_csv.writerow([
                        round(now, 3), stable, raw,
                        detection["name"], round(detection["confidence"], 4),
                    ])
                    if raw != stable:
                        raw_identity_changes.append(change)
                events = tracker.update(vehicles, zones, config.get("exit_zone", []), now)
                for event in events:
                    session_id = event["session_id"]
                    tracker_sessions.add(session_id)
                    phase = event["phase"]
                    events_by_phase[phase] += 1
                    duration = ""
                    if phase == "parked":
                        active = tracker.vehicles.get(event["track_id"])
                        parked_since[session_id] = (
                            active.candidate_since if active is not None else now
                        )
                    elif phase == "exiting" and session_id in parked_since:
                        active = tracker.vehicles.get(event["track_id"])
                        began_exiting = active.outside_since if active is not None else now
                        duration = round(max(0, began_exiting - parked_since[session_id]), 2)
                        durations.append(duration)
                    event_csv.writerow([
                        round(now, 3), session_id, event["track_id"],
                        PHASE_NAMES.get(phase, "未確認"), phase,
                        event.get("space_uid") or "", duration,
                    ])
                occupancy_vehicles = [d for d in vehicles if d["confidence"] >= confidence]
                raw = classify_spaces(occupancy_vehicles, blockers, zones)
                departures = [event["space_uid"] for event in events
                              if event["phase"] == "exiting" and event.get("space_uid")]
                states = space_states.update(raw, now, departures=departures)
                prevented_false_free_frames += sum(
                    raw[uid] == "available" and states[uid] != "available"
                    and uid in space_states.had_vehicle for uid in raw
                )
                for uid, status in states.items():
                    counts[uid][status] += 1

                # 変化がなくても約1秒おきに書き出す。膨大なフレーム単位ログを避ける。
                if states != last_statuses or now - last_logged >= 1:
                    vehicle_counts = Counter(space_for(d["point"], zones)
                                             for d in occupancy_vehicles)
                    obstacle_counts = Counter(space_for(d["point"], zones) for d in blockers)
                    for uid, status in states.items():
                        state_csv.writerow([
                            round(now, 3), uid, STATUS_NAMES[status], status,
                            vehicle_counts.get(uid, 0), obstacle_counts.get(uid, 0),
                        ])
                    last_logged = now
                    last_statuses = states.copy()
                if args.preview or args.save_video:
                    overlay(frame, zones, states, vehicles, blockers)
                    if args.save_video:
                        if video_writer is None:
                            h, w = frame.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                            video_writer = cv2.VideoWriter(
                                str(run_dir / "判定結果_確認用.mp4"), fourcc, fps, (w, h)
                            )
                            if not video_writer.isOpened():
                                raise ValueError("判定結果の動画を書き込めません。--save-video を外してください")
                        video_writer.write(frame)
                    if args.preview:
                        cv2.imshow("Parking research video (q: stop)", frame)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            print("途中で確認を終了しました。処理した範囲だけ記録します。")
                            break
                if frames % 150 == 0:
                    print("処理済み:", frames, "/", total_frames or "不明", "フレーム")
                if args.max_frames and frames >= args.max_frames:
                    print("指定されたテストフレーム数に達しました。")
                    break
    finally:
        cap.release()
        if video_writer:
            video_writer.release()
        if args.preview:
            cv2.destroyAllWindows()
    summary = {
        "video_filename": video.name, "processed_frames": frames,
        "total_frames_reported": total_frames,
        "fps_reported": fps, "video_seconds_processed": round(now, 3),
        "facility_id": config["facility_id"],
        "camera_id": config["camera_id"], "space_count": len(zones),
        "obstacle_model_enabled": bool(config.get("obstacle_model")),
        "observations": summarize_observations(counts, frames),
        "tracked_session_count": len(tracker_sessions),
        "original_yolo_id_count": len(raw_track_ids),
        "stable_id_reassociations": stable_ids.reassociated,
        "ambiguous_id_matches_rejected": stable_ids.ambiguous,
        "unverified_free_frame_blocks": prevented_false_free_frames,
        "tracker_file": tracker_file,
        "tracking_confidence": tracking_confidence,
        "occupancy_confidence": confidence,
        "allow_unverified_initial_empty": space_states.allow_initial_empty,
        "track_id_connections": [
            {"stable_id": stable, "original_yolo_id": raw}
            for stable, raw in raw_identity_changes
        ],
        "phase_change_count": dict(events_by_phase),
        "completed_parking_sessions": len(durations),
        "confirmed_parking_seconds": durations,
        "cloud_uploaded": False,
        "important": "検知結果の集計であり正解率ではありません。状態unknownは安全側の判定です。目視による正解ラベルと照合してください。"
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("完了。結果:", run_dir)
    print("駐車場案内に使う前に、出力と映像を目視で照合してください。")
    return run_dir


def main():
    parser = argparse.ArgumentParser(description="録画動画の車両追跡・駐車枠判定をCSVで確認する")
    parser.add_argument("--video", required=True, help="例: C:\\Users\\Owner\\Desktop\\parking-yolo-starter\\test_house1.mp4")
    parser.add_argument("--config", default="config.json", help="区画の登録情報")
    parser.add_argument("--output", default="reports", help="結果保存先フォルダ")
    parser.add_argument("--preview", action="store_true", help="動画画面を見ながら進める")
    parser.add_argument("--save-video", action="store_true", help="確認用の判定済みMP4も保存")
    parser.add_argument("--max-frames", type=int, default=0, help="最初の指定フレーム数だけ試す")
    args = parser.parse_args()
    try:
        analyze(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.exit("動画を解析できませんでした: " + str(exc))


if __name__ == "__main__":
    main()
