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


PREVIEW_WIDTH = 1080
PREVIEW_HEIGHT = 740
VIDEO_TOP = 108
VIDEO_BOTTOM = 590


def _prepare_preview_text(number, backend):
    """日本語操作パネルを一度だけ描く。動画の上には文字を重ねない。"""
    import numpy as np

    panel = np.empty((PREVIEW_HEIGHT, PREVIEW_WIDTH, 3), dtype=np.uint8)
    panel[:] = (26, 28, 32)
    # OpenCV Hersheyフォントは日本語非対応。PillowとWindowsの日本語
    # フォントを使い、失敗したら読める英語で表示する。
    try:
        from PIL import Image, ImageDraw, ImageFont

        windows_fonts = [
            Path(r"C:\Windows\Fonts\meiryo.ttc"),
            Path(r"C:\Windows\Fonts\YuGothM.ttc"),
            Path(r"C:\Windows\Fonts\msgothic.ttc"),
        ]
        font_path = next((p for p in windows_fonts if p.is_file()), None)
        if not font_path:
            raise FileNotFoundError("日本語フォントがありません")

        title_font = ImageFont.truetype(str(font_path), 29)
        main_font = ImageFont.truetype(str(font_path), 25)
        small_font = ImageFont.truetype(str(font_path), 20)
        canvas = Image.fromarray(cv2.cvtColor(panel, cv2.COLOR_BGR2RGB))
        painter = ImageDraw.Draw(canvas)
        painter.text((22, 12), "外付けUSBカメラの映像を確認してください",
                     font=title_font, fill=(252, 252, 255))
        painter.text((22, 58), f"カメラ番号：{number}　　接続方式：{backend}",
                     font=main_font, fill=(170, 214, 244))
        painter.text((22, 615), "[ S ] 正しいカメラ　　[ N ] 別のカメラ　　[ Q ] 中止",
                     font=main_font, fill=(255, 255, 255))
        painter.text((22, 678), "Sキーで確認後、PowerShell画面で「外付け」と入力します",
                     font=small_font, fill=(188, 197, 209))
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
    except (ImportError, OSError, ValueError):
        # 日本語フォントやPillowがないPCでも操作を止めない。
        instructions = [
            "CHECK YOUR EXTERNAL USB CAMERA",
            f"Camera {number} / Backend {backend}",
            "S = CONFIRM   N = OTHER CAMERA   Q = QUIT",
            "After S, return to PowerShell and type the requested confirmation.",
        ]
        for label, y, size in zip(instructions, (39, 83, 645, 699),
                                  (0.90, 0.75, 0.85, 0.56)):
            cv2.putText(panel, label, (22, y), cv2.FONT_HERSHEY_SIMPLEX,
                        size, (242, 245, 249), 2, cv2.LINE_AA)
        return panel


def render_preview_frame(image, panel):
    """大きなプレビュー領域へ縦横比を維持して表示（画角は切り抜かない）。"""
    import numpy as np

    result = panel.copy()
    h, w = image.shape[:2]
    if w <= 0 or h <= 0:
        return result
    video_width = PREVIEW_WIDTH - 32
    video_height = VIDEO_BOTTOM - VIDEO_TOP - 12
    scale = min(video_width / w, video_height / h)
    display_w = max(1, round(w * scale))
    display_h = max(1, round(h * scale))
    resized = cv2.resize(image, (display_w, display_h),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    x = (PREVIEW_WIDTH - display_w) // 2
    y = VIDEO_TOP + (video_height - display_h) // 2
    result[y:y + display_h, x:x + display_w] = resized
    cv2.rectangle(result, (x - 2, y - 2), (x + display_w + 2, y + display_h + 2),
                  (120, 130, 144), 2, cv2.LINE_AA)
    return result


def preview(camera, number="?", backend="auto"):
    """大きな日本語表示でS=確認、N=別カメラ、Q=中止。"""
    name = "Parking Camera Check (S=OK / N=Next / Q=Quit)"
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(name, PREVIEW_WIDTH, PREVIEW_HEIGHT)
    panel = _prepare_preview_text(number, backend)
    print(f"【確認画面】カメラ番号 {number} / 接続方式 {backend}")
    print("【映像画面の操作】S=このカメラで決定、N=別のカメラ、Q=中止")
    try:
        while True:
            ok, image = camera.read()
            if not ok:
                print("【注意】映像を取得できません。別の番号を選んでください。")
                return "other"
            cv2.imshow(name, render_preview_frame(image, panel))
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
            camera = open_camera(cv2, number, backend, settings.get("camera_manual_exposure"))
            if not camera.isOpened():
                camera.release()
                raise SystemExit("【中止】保存済みの外付けカメラに接続できません。準備から確認してください")
        else:
            camera, backend = try_camera(number)
            if camera is None:
                print("【未検出】その番号ではカメラを開けません。別の番号を試してください。")
                continue

        try:
            answer = preview(camera, number=number, backend=backend)
        finally:
            camera.release()
            cv2.destroyAllWindows()

        if answer == "quit":
            raise SystemExit("【中止】カメラ映像が確認されなかったため判定は開始しません")
        if answer == "other":
            if args.check_only:
                raise SystemExit("【中止】保存されたカメラは外付けでない可能性があります。準備から選び直してください")
            continue

        check = input("Camoではない外付けUSB Webカメラの映像なら「外付け」と入力: ").strip()
        if check != "外付け":
            if args.check_only:
                raise SystemExit("【中止】外付けカメラの確認が完了していません")
            continue

        if args.check_only:
            print("【確認完了】保存された外付けカメラの映像を確認しました。")
            return

        old_source = settings.get("source")
        old_backend = settings.get("camera_backend")
        old_kind = str(settings.get("camera_kind") or "usb").lower()
        was_verified = settings.get("camera_verified_external") is True
        # 既存の設定はバックアップしてから変更する。カメラ変更時は枠座標を再登録。
        backup = path.with_name("config_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        shutil.copy2(path, backup)
        settings["source"] = number
        settings["camera_backend"] = backend
        # この選択画面は「Camoではない外付けUSB Webカメラ」を
        # 目視確認する専用の画面。以前のCamo設定を残さない。
        settings["camera_kind"] = "usb"
        settings["camera_verified_external"] = True
        settings["camera_verified_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if (not was_verified or old_source != number or old_backend != backend
                or old_kind != "usb"):
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
