#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日光のYOLO録画ログを、ユーザーアプリの過去録画ビュー用CSVに変換する。

録画から得た判定だけを転記。監視の結果は現在の空きには反映しない。
無限ループ再生は最初の1周だけを利用し、時刻の逆行を防ぐ。
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from nikko_video_config import read_settings, checked_config

ALLOWED_STATUSES = {
    "available": "空き", "occupied": "駐車中",
    "blocked": "障害物あり", "unknown": "確認できない",
}


def convert_recording_log(log_path, output_path, *, duration, space_uids):
    if duration <= 0 or duration > 86400:
        raise ValueError("動画の長さが不正です")
    with Path(log_path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"録画経過秒数", "区画UID", "判定状態", "周回"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("元CSVはmonitor.pyの「区画状態の変化.csv」を選んでください")
        entries = []
        last_by_uid = {}
        previous = -1.0
        for item in reader:
            if int(item["周回"]) != 1:
                continue
            elapsed = float(item["録画経過秒数"])
            uid = item["区画UID"]
            status = item["判定状態"]
            if (uid not in space_uids or status not in ALLOWED_STATUSES or
                    not 0 <= elapsed <= duration + 1):
                raise ValueError("録画ログの区画・時刻・判定が不正です")
            if elapsed < previous:
                raise ValueError("録画ログの時刻が逆行しています")
            previous = elapsed
            entries.append((min(elapsed, duration), uid, status))
            last_by_uid[uid] = status
    if not entries or set(last_by_uid) != set(space_uids):
        raise ValueError("撮影範囲内の登録済み区画をすべて判定できていません。YOLOを1周以上実行してください")
    output = Path(output_path)
    if output.resolve() == Path(log_path).resolve():
        raise ValueError("元の診断ログへ上書きしません")
    if output.exists():
        raise FileExistsError("出力済みの録画CSVは上書きできません")
    # 「0秒=未確認」は、録画前に検出済みとは主張しないための初期表示。
    rows = [(0.0, uid, "unknown") for uid in space_uids] + entries
    rows.extend((float(duration), uid, last_by_uid[uid]) for uid in SPACE_UIDS)
    rows.sort(key=lambda row: row[0])
    with output.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["動画の時刻(秒)", "駐車枠ID", "判定", "判定コード"])
        for elapsed, uid, status in rows:
            writer.writerow([f"{elapsed:.3f}", uid, ALLOWED_STATUSES[status], status])
    return output


def video_duration(video):
    import cv2
    from video_replay import validate_video
    capture = cv2.VideoCapture(str(validate_video(video)))
    try:
        if not capture.isOpened():
            raise ValueError("録画ファイルを開けません")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if not 1 <= fps <= 120 or count <= 0:
            raise ValueError("動画のFPSまたはコマ数を取得できません")
        return count / fps
    finally:
        capture.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description="日光・YOLO録画結果を利用者向け過去録画CSVへ変換")
    parser.add_argument("--log", required=True, help="monitor.py出力の区画状態の変化.csv")
    parser.add_argument("--config", default="config_nikko_video_demo.json",
                        help="道の駅日光の録画実験専用設定")
    parser.add_argument("--video", required=True, help="再解析した元動画")
    parser.add_argument("--output", default="", help="出力先（元CSVとは別）")
    args = parser.parse_args(argv)
    log = Path(args.log).resolve()
    output = Path(args.output).resolve() if args.output else log.with_name("駐車枠の状態_利用者アプリ用.csv")
    config = checked_config(read_settings(args.config))
    result = convert_recording_log(log, output, duration=video_duration(args.video),
                                   space_uids=config["space_uids"])
    print("【録画用CSV生成】", result)
    print("管理者アプリの「録画実験：...の結果を再生」から読み込んでください。")
    print("【重要】このCSVは過去の録画です。現在の空き情報ではありません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
