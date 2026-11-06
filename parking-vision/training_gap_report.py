# -*- coding: utf-8 -*-
"""Report existing human-reviewed label coverage and gaps without changing data."""
from __future__ import annotations

import argparse
import json
from collections import Counter

from unified_annotation_dataset import (
    AnnotationWorkspace, TASKS, VEHICLE_CLASSES, OBSTACLE_CLASSES,
    LAYOUT_CLASSES, workspace_source, validate_task_label,
)

DISPLAY = {"vehicle": VEHICLE_CLASSES, "obstacle": OBSTACLE_CLASSES,
           "layout": LAYOUT_CLASSES}


def build_report(ws):
    report = {"images": len(ws.photos), "tasks": {}}
    for task in TASKS:
        counts = Counter()
        missing = []
        negatives = 0
        for photo in ws.photos:
            content, saved = ws.read(photo, task)
            if not saved:
                missing.append(photo["relative"].as_posix())
                continue
            if not content.strip():
                negatives += 1
                continue
            validate_task_label(task, content)
            for label in content.splitlines():
                if label.strip():
                    cls = int(label.split()[0])
                    counts[cls] += 1
        report["tasks"][task] = {
            "reviewed": len(ws.photos) - len(missing),
            "unreviewed": len(missing),
            "negatives": negatives,
            "objects_total": sum(counts.values()),
            "classes": {str(i): {"name": name, "count": counts[i]}
                        for i, name in DISPLAY[task].items()},
            "unreviewed_examples": missing[:10],
        }
    return report


def main():
    parser = argparse.ArgumentParser(
        description="研究用の追加学習候補と未登録写真の件数をチェック（読み取り専用）")
    parser.add_argument("--workspace", default="annotation_workspaces/photos_242")
    parser.add_argument("--images", help="元画像を別のフォルダへ移した場合のみ指定")
    parser.add_argument("--json", help="必要な場合だけJSONレポートを保存")
    args = parser.parse_args()
    try:
        ws = AnnotationWorkspace(workspace_source(args.workspace, args.images),
                                 args.workspace)
        data = build_report(ws)
        print(f"元画像: {data['images']}枚")
        for task in TASKS:
            info = data["tasks"][task]
            print(f"\n[{task}] 登録済 {info['reviewed']}/{data['images']}枚 "
                  f"対象なし {info['negatives']}枚 対象 {info['objects_total']}個")
            for cls, info_cls in info["classes"].items():
                print(f"  {cls}: {info_cls['name']} = {info_cls['count']}個")
            if info["unreviewed"]:
                print(f"  ※ 未登録 {info['unreviewed']}枚。"
                      "未登録を『対象なし』と解釈しません。")
        if args.json:
            from pathlib import Path
            output = Path(args.json).expanduser().resolve()
            if output.exists():
                parser.error(f"既存ファイルを上書きできません: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
