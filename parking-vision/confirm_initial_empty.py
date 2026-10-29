#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-time, operator-verified empty spaces for a local camera experiment.

This never changes Supabase directly and does not make UNKNOWN look empty
without a conscious on-site check. The approval expires automatically.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from shutil import copy2


VALID_FOR_MINUTES = 15


def read_labels(config):
    labels = config.get("space_labels") or {}
    if isinstance(labels, dict):
        return {str(k): str(v) for k, v in labels.items()}
    if isinstance(labels, list):
        return {str(uid): str(label) for uid, label in zip(
            config.get("space_uids", []), labels
        )}
    return {}


def choose_verified_empty(config, answer):
    """Accept only numbered spaces that already have camera-calibrated zones."""
    uids = [str(uid) for uid in config.get("space_uids", [])]
    zones = config.get("space_zones") or {}
    if not uids or not all(uid in zones and len(zones[uid]) >= 3 for uid in uids):
        raise ValueError("6区画のカメラ座標登録が完了していません。先に確認してください")
    parts = [part.strip() for part in answer.replace("、", ",").split(",")]
    if not parts or not any(parts):
        return []
    chosen = []
    for part in parts:
        if not part.isdecimal():
            raise ValueError("区画番号を数字で入力してください（例：3,6）")
        index = int(part)
        if not 1 <= index <= len(uids):
            raise ValueError(f"区画番号{part}は登録範囲外です")
        uid = uids[index - 1]
        if uid not in chosen:
            chosen.append(uid)
    return chosen


def main():
    import argparse
    parser = argparse.ArgumentParser(description="カメラの空車確認済み区画だけ一時的に承認")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()
    path = Path(args.config).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if config.get("facility_id") != "home-test-001":
        raise SystemExit("【中止】自宅駐車場以外の設定は変更しません")
    labels = read_labels(config)
    uids = list(map(str, config.get("space_uids", [])))
    print("========== 自宅駐車場・実地確認済みの空き区画 ==========")
    print("【重要】最初にYOLOを停止し、カメラ映像と実際の駐車場を確認してください。")
    print("【注意】人、カラーコーン、カート、車がある区画は空車として登録しないでください。")
    print("【注意】カメラで死角になっている場所も空きとして登録しないでください。")
    for number, uid in enumerate(uids, start=1):
        print(f"  {number}番  {uid}  {labels.get(uid, '')}")
    answer = input("現地で空車を確認した区画番号を半角数字で入力（例: 3,6 / なしはEnter）: ")
    try:
        selected = choose_verified_empty(config, answer)
    except ValueError as exc:
        raise SystemExit(f"【中止】{exc}") from exc
    if not selected:
        print("【変更なし】登録を行いませんでした")
        return
    print("承認対象: " + ", ".join(selected))
    print(f"この承認は{VALID_FOR_MINUTES}分で失効します。車が新しく入ればカメラの判定を優先します。")
    confirmation = input("対象の全区画が今まさに安全に空いていると確認したら「確認」と入力: ")
    if confirmation != "確認":
        print("【中止】設定を変更しませんでした")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name("config_backup_initial_empty_" + stamp + ".json")
    copy2(path, backup)
    config["initially_confirmed_empty_uids"] = selected
    config["initial_empty_verified_at"] = datetime.now(timezone.utc).isoformat()
    config["initial_empty_valid_seconds"] = VALID_FOR_MINUTES * 60
    config["allow_unverified_initial_empty"] = False
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"【保存完了】{len(selected)}区画。保存前のバックアップ: {backup.name}")
    print("【次の操作】ライブ共有を再起動し、管理アプリで状態を確認してください")


if __name__ == "__main__":
    main()
