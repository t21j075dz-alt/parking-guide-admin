#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一動画/区画/モデルを2種類の追跡方式で処理する卒業研究用の比較ツール。

実測正解率は出さず、セッション分裂や不明判定などの指標だけを比較する。
結果には元映像やプレートは保存せず、実験CSV/JSONのみ出力する。
"""
from __future__ import annotations

import argparse
from argparse import Namespace
import csv
import json
from pathlib import Path
import tempfile

from analyze_video import analyze


def report_row(label: str, summary: dict) -> dict:
    return {
        "tracker": label,
        "frames": summary["processed_frames"],
        "original_yolo_id_count": summary.get("original_yolo_id_count", 0),
        "tracked_session_count": summary["tracked_session_count"],
        "stable_id_reassociations": summary.get("stable_id_reassociations", 0),
        "ambiguous_id_matches_rejected": summary.get("ambiguous_id_matches_rejected", 0),
        "unverified_free_frame_blocks": summary.get("unverified_free_frame_blocks", 0),
        "confirmed_parking_sessions": summary.get("completed_parking_sessions", 0),
    }


def main():
    ap = argparse.ArgumentParser(description="BoT-SORTとByteTrackの追跡結果を同一動画で比較")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--video", required=True)
    ap.add_argument("--output", default="reports_comparison")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    video_path = Path(args.video).resolve()
    if not config_path.is_file() or not video_path.is_file():
        ap.error("指定のconfig.jsonまたは動画が存在しません")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=True, parents=True)
    if not (Path(__file__).parent / "botsort-parking.yaml").is_file():
        ap.error("botsort-parking.yaml が見つかりません。GitHub最新版をご利用ください")

    comparisons = []
    for label, tracker in (
        ("botsort-parking", str((Path(__file__).parent / "botsort-parking.yaml").resolve())),
        ("bytetrack-standard", "bytetrack.yaml"),
    ):
        overridden = dict(config)
        overridden["tracker_file"] = tracker
        with tempfile.TemporaryDirectory() as tempdir:
            test_config = Path(tempdir) / "config.json"
            test_config.write_text(json.dumps(overridden, ensure_ascii=False), encoding="utf-8")
            print("\n=== 実験条件:", label, "===")
            run_dir = analyze(Namespace(
                config=str(test_config), video=str(video_path),
                output=str(output / label), preview=False,
                save_video=False, max_frames=args.max_frames,
            ))
        result = json.loads((run_dir / "分析結果.json").read_text(encoding="utf-8"))
        comparisons.append(report_row(label, result))

    csv_path = output / "追跡方式比較.csv"
    keys = list(comparisons[0])
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(comparisons)
    (output / "追跡方式比較.json").write_text(
        json.dumps({
            "video": video_path.name,
            "metrics_only": True,
            "note": "IDの発行数や結び直し回数は追跡精度そのものではありません。動画に正解の車両IDを付けてIDF1/HOTA等の検証が必要です。",
            "results": comparisons,
        }, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    print("\n比較完了:", csv_path)
    for item in comparisons:
        print(item)


if __name__ == "__main__":
    main()
