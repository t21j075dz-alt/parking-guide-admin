#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目視で作った正解CSVと駐車枠の状態.csvを比較（未確認を空きと扱わない）。

正解CSVの列：動画の時刻(秒),駐車枠ID,正解コード
正解コード: available/occupied/blocked/unknown。unknownは採点対象外。
解析データは1秒間隔＋状態変化時点なので、指定時刻以前の最新行で評価する。
"""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

LABELS = ("available", "occupied", "blocked", "unknown")


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def evaluate(prediction_rows, ground_truth_rows):
    history = defaultdict(list)
    for row in prediction_rows:
        uid = row.get("駐車枠ID")
        status = row.get("判定コード")
        try:
            at = float(row.get("動画の時刻(秒)", ""))
        except (ValueError, TypeError):
            continue
        if uid and status in LABELS and at >= 0:
            history[uid].append((at, status))
    timelines = {}
    for uid, rows in history.items():
        rows.sort()
        timelines[uid] = ([t for t, _ in rows], [label for _, label in rows])

    confusion = Counter()
    matched = skipped = unavailable = false_free = 0
    detail = []
    for row in ground_truth_rows:
        uid = row.get("駐車枠ID")
        truth = row.get("正解コード")
        if truth not in LABELS:
            raise ValueError(f"{uid}: 正解コードは{', '.join(LABELS)}から選んでください")
        if truth == "unknown":
            skipped += 1  # 目視でも分からないデータは採点しない
            continue
        try:
            at = float(row.get("動画の時刻(秒)", ""))
        except (TypeError, ValueError):
            raise ValueError("正解CSVの動画の時刻(秒)が不正です") from None
        if at < 0:
            raise ValueError("時刻は0以上を指定してください")
        if uid not in timelines:
            unavailable += 1
            continue
        times, states = timelines[uid]
        index = bisect_right(times, at) - 1
        if index < 0:
            unavailable += 1
            continue
        predicted = states[index]
        matched += 1
        confusion[(truth, predicted)] += 1
        if predicted == "available" and truth != "available":
            false_free += 1
        detail.append({
            "動画の時刻(秒)": at,
            "駐車枠ID": uid,
            "正解コード": truth,
            "予測コード": predicted,
            "一致": int(truth == predicted),
            "誤った空き案内": int(predicted == "available" and truth != "available"),
        })

    non_unknown_predictions = sum(
        value for (truth, pred), value in confusion.items() if pred != "unknown"
    )
    correct = sum(value for (truth, pred), value in confusion.items() if truth == pred)
    by_label = {}
    for label in LABELS[:-1]:
        tp = confusion[(label, label)]
        fp = sum(confusion[(other, label)] for other in LABELS[:-1] if other != label)
        fn = sum(confusion[(label, other)] for other in LABELS if other != label)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
        by_label[label] = {
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }
    summary = {
        "evaluated": matched,
        "ground_truth_unknown_skipped": skipped,
        "prediction_unavailable": unavailable,
        "exact_accuracy_including_unknown": round(correct/matched, 4) if matched else None,
        "coverage_excluding_unknown": round(non_unknown_predictions/matched, 4) if matched else None,
        "false_available_count": false_free,
        "false_available_rate": round(false_free/matched, 4) if matched else None,
        "by_label": by_label,
        "confusion": [
            {"truth": a, "prediction": b, "count": c}
            for (a, b), c in sorted(confusion.items())
        ],
        "caution": "人手正解データの行だけで評価した結果。サンプルが少ない場合、駐車場全体の精度とは言えません。",
    }
    return summary, detail


def main():
    parser = argparse.ArgumentParser(description="駐車場区画の正解ラベルと予測を比較")
    parser.add_argument("--predicted", required=True, help="YOLOが作成した駐車枠の状態.csv")
    parser.add_argument("--truth", required=True, help="人手で確認した正解CSV")
    parser.add_argument("--output", default="evaluation")
    args = parser.parse_args()
    summary, detail = evaluate(read_csv(args.predicted), read_csv(args.truth))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output/"区画評価結果.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output/"区画評価明細.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["動画の時刻(秒)", "駐車枠ID", "正解コード",
                                                "予測コード", "一致", "誤った空き案内"])
        writer.writeheader()
        writer.writerows(detail)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
