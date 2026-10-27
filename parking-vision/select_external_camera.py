#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外付けWebカメラを映像で確認する。番号と内蔵/外付けの対応は決めつけない。

Windowsではカメラ番号が0とは限らず、USBの差し直しでも変わる。
利用者が実際の映像を見て外付けと確認しない限り選択を保存しない。
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil

import cv2

from camera_recording import open_camera


def preview(camera):
    """Sで確認、Nで別のカメラ、Qで中止。"""
    name = "Web camera confirmation (S=external / N=other / Q=quit)"
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    try:
        while True:
            ok, image = camera.read()
            if not ok:
                print("【注意】映像を取得できません。別の番号を選んでください。")
                return "other"
            view = image.copy()
            cv2.putText(
                view, "Is this your EXTERNAL USB camera? S=yes N=no Q=quit",
                (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .53, (10, 255, 20), 2
            )
            cv2.imshow(name, view)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("s"), ord("S")):
                return "select"
            if key in (ord("n"), ord("N")):
                return "other"
            if key in (ord("q"), ord("Q"), 27):
                return "quit"
    finally:
        cv2.destroyWindow(name)


def try_camera(number):
    """開けたバックエンドを記録し、実行時も同じ種類で開く。"""
    for backend in ("dshow", "msmf", "auto"):
        camera = open_camera(cv2, number, backend)
        if camera.isOpened():
            ok, _ = camera.read()
            if ok:
                return camera, backend
        camera.release()
    return None, None


def main():
    parser = argparse.ArgumentParser(description="外付けUSB Webカメラを確認")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--check-only", action="store_true",
                        help="保存済みのカメラが今も外付けか確認し、設定は変更しない")
    args = parser.parse_args()

    path = Path(args.config)
    settings = json.loads(path.read_text(encoding="utf-8"))
    print("【外付けカメラの確認】内蔵カメラは録画・YOLO判定に使用しません。")
    print("番号0/1/2は機種や接続状態で変わります。必ず実際の映像で確認してください。")
    print("内蔵カメラを一切開きたくない場合は、Windowsのデバイスマネージャーで先に無効化してください。")
    print("別アプリでカメラを使用中なら、そのアプリを閉じてください。")

    while True:
        if args.check_only:
            number = settings.get("source")
            if not isinstance(number, int) or number < 0:
                raise SystemExit("【中止】設定済みの外付けカメラ番号がありません。準備からやり直してください")
        else:
            raw = input("外付けカメラの番号を入力（例: 1 / qで中止）: ").strip()
            if raw.lower() == "q":
                raise SystemExit("【中止】カメラは登録しませんでした")
            if not raw.isdecimal():
                print("0以上の番号を入力してください。")
                continue
            number = int(raw)

        if args.check_only:
            backend = str(settings.get("camera_backend", "auto"))
            camera = open_camera(cv2, number, backend)
            if not camera.isOpened():
                camera.release()
                raise SystemExit("【中止】保存済みの外付けカメラに接続できません。準備から確認してください")
        else:
            camera, backend = try_camera(number)
            if camera is None:
                print("【未検出】その番号ではカメラを開けません。別の番号を試してください。")
                continue

        try:
            answer = preview(camera)
        finally:
            camera.release()
            cv2.destroyAllWindows()

        if answer == "quit":
            raise SystemExit("【中止】カメラ映像が確認されなかったため判定は開始しません")
        if answer == "other":
            if args.check_only:
                raise SystemExit("【中止】保存されたカメラは外付けでない可能性があります。準備から選び直してください")
            continue

        check = input("外付けUSB Webカメラの映像だと確認できたら「外付け」と入力: ").strip()
        if check != "外付け":
            if args.check_only:
                raise SystemExit("【中止】外付けカメラの確認が完了していません")
            continue

        if args.check_only:
            print("【確認完了】保存された外付けカメラの映像を確認しました。")
            return

        old_source = settings.get("source")
        old_backend = settings.get("camera_backend")
        was_verified = settings.get("camera_verified_external") is True
        # 既存の設定はバックアップしてから変更する。カメラ変更時は枠座標を再登録。
        backup = path.with_name("config_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        shutil.copy2(path, backup)
        settings["source"] = number
        settings["camera_backend"] = backend
        settings["camera_verified_external"] = True
        settings["camera_verified_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if not was_verified or old_source != number or old_backend != backend:
            settings["space_zones"] = {}
            settings["entry_zone"] = []
            settings["exit_zone"] = []
            print("【再設定】撮影範囲が変わる可能性があるため、駐車枠を登録し直します。")
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"【保存】外付けカメラ番号 {number} / 接続方式 {backend}")
        print(f"【設定バックアップ】{backup}")
        return


if __name__ == "__main__":
    main()
