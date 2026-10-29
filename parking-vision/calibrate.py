#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外付けWebカメラのライブ映像で駐車枠を登録する。

明るすぎる画像を「暗く加工しただけ」で正しい映像だと誤認しないよう、
露出操作は実際のUSBカメラに対して試みる。カメラが未対応なら明示する。
座標は画面幅・高さの比率で保存するため、元動画とプレビューの解像度が
異なっても一致する。駐車枠が見えなければ保存せず終了できる。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import cv2

from camera_exposure import is_valid_manual_exposure, step_manual_exposure
from camera_recording import open_camera
from camera_profiles import capture_preferences
from zone_geometry import normalize_corners


WINDOW = "Parking space setup - LIVE camera / SPACE = freeze"


def is_live_source(source):
    """保存動画・静止画は従来の1コマ方式、WebカメラとRTSPはライブ表示。"""
    if isinstance(source, int):
        return True
    if isinstance(source, str):
        return source.isdecimal() or source.lower().startswith(("rtsp://", "rtsps://"))
    return False


def preview_dimensions(width, height, max_width=1200, max_height=740):
    """ウィンドウが画面からはみ出さないよう、縦横比を保って縮小する。"""
    factor = min(1.0, max_width / width, max_height / height)
    return max(1, round(width * factor)), max(1, round(height * factor))


def scale_frame(frame):
    h, w = frame.shape[:2]
    new_w, new_h = preview_dimensions(w, h)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA) if (new_w, new_h) != (w, h) else frame


def whiteout_ratio(frame):
    """ほぼ全白の画素割合。画像の品質警告に使い、自動補正はしない。"""
    # RGB値が全て250以上の画素は元の細部がほぼ残っていない。
    return float((frame.min(axis=2) >= 250).mean())


def labeled_line(image, label, position, scale=.58):
    """白飛びした背景でも文字が読めるよう、文字の縁を黒で表示する。"""
    x, y = position
    cv2.putText(image, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (255, 255, 255), 2, cv2.LINE_AA)


def main():
    parser = argparse.ArgumentParser(description="ライブ映像を見ながら駐車枠を登録")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--source", help="設定ファイルより優先する動画/カメラ入力")
    args = parser.parse_args()
    path = Path(args.config)
    config = json.loads(path.read_text(encoding="utf-8"))
    source = args.source if args.source is not None else config.get("source", 0)
    if isinstance(source, str) and source.isdecimal():
        source = int(source)
    names = [str(uid) for uid in config.get("space_uids", [])]
    if not names:
        raise SystemExit("【中止】登録する駐車枠IDがありません")

    requested_width, requested_height, requested_fps = capture_preferences(config)
    camera = open_camera(
        cv2, source, config.get("camera_backend", "auto"),
        config.get("camera_manual_exposure"),
        requested_width, requested_height, requested_fps,
    )
    if not camera.isOpened():
        camera.release()
        raise SystemExit("【エラー】外付けWebカメラを開けません。選択した番号を確認してください")

    live = is_live_source(source)
    areas = dict(config.get("space_zones") or {})
    mode = 0
    phase = "spaces"
    clicked = []
    frame = None
    raw_dimensions = None  # 保存するのは縮小前の実際の映像サイズ
    frozen = not live
    changed = False
    manual = config.get("camera_manual_exposure")
    if not is_valid_manual_exposure(manual):
        manual = None

    # ログは日本語で明示する。OpenCVのputTextは日本語に非対応。
    print("")
    print("========== 外付けWebカメラ：駐車枠の設定 ==========")
    print("【重要】この画面はライブ映像です。駐車枠をはっきり映してから登録してください。")
    print("【P】USBカメラの詳細設定（DirectShow対応機のみ）")
    print("【- / +】実際のカメラの露出を暗く/明るく（対応機種のみ）")
    print("【A】自動露出に戻す（対応機種のみ）")
    print("【Space】映像の静止/再開。映像をクリックすると自動で静止します。")
    print("【左クリック4回】四隅を登録（クリックの順番は自由） / 【Backspace】1点戻す / 【R】対象枠を削除")
    print("【Enter / S】次の区画 / 【E】入口範囲 / 【X】出口範囲")
    print("【Q】保存して終了 / 【Esc】今回の変更を保存せず終了")
    print("【注意】画像の見かけだけを暗くしても、白飛びした細部は戻りません。")
    print("")

    def current_name():
        return names[mode] if phase == "spaces" and mode < len(names) else phase

    def mark(event, x, y, flags, param):
        nonlocal frozen
        if event != cv2.EVENT_LBUTTONDOWN or frame is None:
            return
        if not 0 <= x < frame.shape[1] or not 0 <= y < frame.shape[0]:
            return  # 操作説明の黒帯は区画ではない
        if current_name() == "complete":
            return
        if live and not frozen:
            frozen = True
            print("【映像を静止】4か所をクリックして区画を指定してください。")
        if len(clicked) < 4:
            clicked.append([round(x / frame.shape[1], 5), round(y / frame.shape[0], 5)])

    try:
        # USBカメラの最初の不安定な自動露出を使わない。動画では先頭を使う。
        if live:
            end_warmup = time.monotonic() + .7
            while time.monotonic() < end_warmup:
                ok, newest = camera.read()
                if ok and newest is not None:
                    raw_dimensions = (newest.shape[1], newest.shape[0])
                    frame = scale_frame(newest)
        if frame is None:
            ok, newest = camera.read()
            if not ok or newest is None:
                raise RuntimeError("カメラの映像を取得できません")
            raw_dimensions = (newest.shape[1], newest.shape[0])
            frame = scale_frame(newest)

        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WINDOW, mark)
        while True:
            if live and not frozen:
                ok, newest = camera.read()
                if not ok or newest is None:
                    raise RuntimeError("【エラー】Webカメラの映像が途切れました。枠の変更は保存していません。")
                raw_dimensions = (newest.shape[1], newest.shape[0])
                frame = scale_frame(newest)

            h, w = frame.shape[:2]
            view = frame.copy()
            for uid, polygon in areas.items():
                if len(polygon) < 3:
                    continue
                points = [(round(p[0] * w), round(p[1] * h)) for p in polygon]
                for a, b in zip(points, points[1:] + points[:1]):
                    cv2.line(view, a, b, (0, 160, 255), 3, cv2.LINE_AA)
                labeled_line(view, uid, points[0])

            if clicked:
                positions = [(round(p[0] * w), round(p[1] * h)) for p in clicked]
                for n, p in enumerate(positions):
                    cv2.circle(view, p, 8, (0, 0, 0), 5)
                    cv2.circle(view, p, 6, (0, 225, 255), -1)
                    labeled_line(view, str(n + 1), (p[0] + 12, p[1] - 12), .57)
                for a, b in zip(positions, positions[1:]):
                    cv2.line(view, a, b, (0, 240, 255), 2, cv2.LINE_AA)

            # 画面内を白い文字で埋めない。読みやすい黒い操作帯を下に設置。
            view = cv2.copyMakeBorder(view, 0, 104, 0, 0, cv2.BORDER_CONSTANT, value=(24, 24, 24))
            state = "PAUSED" if frozen else "LIVE"
            white = whiteout_ratio(frame)
            alert = " WHITEOUT! Check exposure" if white > .25 else ""
            exposure = "auto / unknown" if manual is None else str(manual)
            cv2.putText(view, f"{state} | Zone: {current_name()} | corners: {len(clicked)}/4",
                        (12, h + 27), cv2.FONT_HERSHEY_SIMPLEX, .68, (255, 255, 255), 2)
            cv2.putText(view, f"Exposure: {exposure} | Bright white: {white*100:.0f}%{alert}",
                        (12, h + 53), cv2.FONT_HERSHEY_SIMPLEX, .56,
                        (0, 130, 255) if white > .25 else (185, 225, 190), 2)
            cv2.putText(view, "SPACE Pause/Live  - Darker  + Brighter  P Camera settings  A Auto",
                        (12, h + 76), cv2.FONT_HERSHEY_SIMPLEX, .51, (235, 235, 235), 1)
            cv2.putText(view, "Click 4 corners | Q Save/Exit | ESC Cancel | Backspace Undo",
                        (12, h + 96), cv2.FONT_HERSHEY_SIMPLEX, .50, (235, 235, 235), 1)
            cv2.imshow(WINDOW, view)

            key = cv2.waitKey(30) & 0xFF
            if len(clicked) == 4:
                label = current_name()
                try:
                    ordered = normalize_corners(clicked)
                except ValueError as exc:
                    print(f"【登録し直してください】{label}：{exc}")
                    clicked.clear()
                    continue
                areas[label] = ordered
                changed = True
                clicked.clear()
                print(f"【登録】{label}（四隅を自動で正しい順序に並べました）")
                if phase == "spaces":
                    mode += 1
                    if mode >= len(names):
                        phase = "entry_zone"
                elif phase == "entry_zone":
                    phase = "exit_zone"
                else:
                    phase = "complete"

            if key in (27,):  # Esc: no save (also no exposure setting save)
                print("【中止】区画と露出の変更は設定ファイルに保存していません")
                return
            if key in (ord("q"), ord("Q")):
                break
            if key == ord(" "):
                if live:
                    frozen = not frozen
                    if not frozen:
                        clicked.clear()  # 違うフレームの点を混ぜない
            if key in (ord("-"), ord("_"), ord("+"), ord("="), ord("["), ord("]")):
                if not live:
                    print("【注意】録画ファイルにはカメラの露出設定を適用できません")
                    continue
                direction = -1 if key in (ord("-"), ord("_"), ord("[")) else 1
                success, value = step_manual_exposure(camera, cv2, manual, direction)
                if success:
                    manual = value
                    config["camera_manual_exposure"] = manual
                    changed = True
                    frozen = False
                    clicked.clear()
                    print(f"【露出変更】カメラの露出 = {manual}（小さい値ほど暗い）")
                else:
                    print("【未対応】このカメラでは露出を直接変更できません。"
                          "Pキーのカメラ詳細設定または付属ソフトで自動露出をOFFにしてください")
            if key in (ord("a"), ord("A")) and live:
                try:
                    accepted = camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, .75)
                except (AttributeError, OSError):
                    accepted = False
                if accepted:
                    manual = None
                    config.pop("camera_manual_exposure", None)
                    changed = True
                    frozen = False
                    clicked.clear()
                    print("【自動露出】カメラに自動露出を要求しました（機器により反映されない場合あり）")
                else:
                    print("【未対応】自動露出を変更できません。Pキーか付属ソフトで操作してください")
            if key in (ord("p"), ord("P")) and live:
                if config.get("camera_backend") == "dshow":
                    print("【詳細設定】カメラのExposure/露出を下げ、AutoをOFFにしてください")
                    try:
                        camera.set(cv2.CAP_PROP_SETTINGS, 0)
                    except (AttributeError, OSError):
                        print("【未対応】詳細設定画面を開けませんでした")
                    frozen = False
                    clicked.clear()
                else:
                    print("【未対応】詳細設定はDirectShowカメラ向けです。"
                          "外付けカメラの付属ソフトまたはWindowsカメラ設定から露出を調整してください")
            if key in (8, 127) and clicked:
                clicked.pop()
            if key in (ord("r"), ord("R")):
                clicked.clear()
                if current_name() in areas:
                    areas.pop(current_name())
                    changed = True
                    print("【削除】対象区画の登録を解除しました")
            if key in (ord("s"), ord("S"), 13):
                clicked.clear()
                if phase == "spaces":
                    mode += 1
                    if mode >= len(names):
                        phase = "entry_zone"
                elif phase == "entry_zone":
                    phase = "exit_zone"
                else:
                    phase = "complete"
            if key in (ord("e"), ord("E")):
                clicked.clear()
                phase = "entry_zone"
            if key in (ord("x"), ord("X")):
                clicked.clear()
                phase = "exit_zone"

        if changed:
            # 上書き前にバックアップ。キャンセル時は一切書き込まない。
            import shutil
            from datetime import datetime
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = path.with_name("config_backup_calibrate_" + stamp + ".json")
            shutil.copy2(path, backup)
            config["space_zones"] = {
                uid: poly for uid, poly in areas.items() if uid in names
            }
            for key in ("entry_zone", "exit_zone"):
                if key in areas:
                    config[key] = areas[key]
            # Camo/USB別の正規化座標に、登録時の実画像サイズと入力を記録。
            # 解像度が変わっても縦横比が同じなら利用可能。
            if live and raw_dimensions:
                config["calibration_capture"] = {
                    "width": raw_dimensions[0],
                    "height": raw_dimensions[1],
                    "source": str(source),
                    "kind": str(config.get("camera_kind", "usb")).lower(),
                }
            # config.jsonはPythonが読めるUTF-8 BOMなしで保存。
            path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            print(f"【保存】{path} （バックアップ：{backup.name}）")
        else:
            print("【変更なし】既存の区画設定はそのままです")
        print(f"【登録済み】{len(config.get('space_zones', {}))}区画")
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
