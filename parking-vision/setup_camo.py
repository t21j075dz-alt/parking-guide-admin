#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iPhone/Camoの映像を画面で確認し、自宅用の独立したカメラ設定を保存する。

USBカメラのconfig.jsonや区画位置は絶対に上書きしない。
画像はインターネットに送らない。映像そのものも保存しない。
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import time

from camera_profiles import fit_preview_dimensions
from camera_recording import open_camera


HERE = Path(__file__).resolve().parent
PROFILE = HERE / "config_camo.json"


def camera_image(cv2, index, backend):
    """OpenCV上の番号がiPhoneの映像かをユーザーが確認するための取得。"""
    cap = open_camera(cv2, index, backend)
    if not cap.isOpened():
        cap.release()
        return None, None
    # 一部の仮想カメラは映像が安定するまで少し時間が必要。
    deadline = time.monotonic() + 3
    latest = None
    while time.monotonic() < deadline:
        ok, frame = cap.read()
        if ok and frame is not None:
            latest = frame
            break
        time.sleep(0.1)
    if latest is None:
        cap.release()
        return None, None
    return cap, latest


def pick_camera(cv2, index, backend):
    if index is None:
        print("【カメラ番号】WindowsのCamo Studioで仮想カメラを有効にしてください。")
        print("【一覧】使用できるOpenCVのカメラ番号を調べます。")
        detected = []
        for number in range(8):
            cap, image = camera_image(cv2, number, backend)
            if cap is not None:
                detected.append(number)
                print(f"  {number}: {image.shape[1]}x{image.shape[0]} の映像を取得できます")
                cap.release()
        if not detected:
            raise RuntimeError("Camoのカメラが見つかりません。Camo Studioの映像と仮想カメラを確認してください")
        entered = input(f"Camoのカメラ番号を入力してください {detected}: ").strip()
        if not entered.isdecimal() or int(entered) not in detected:
            raise ValueError("利用できるカメラ番号を入力してください")
        index = int(entered)

    cap, image = camera_image(cv2, index, backend)
    if cap is None:
        raise RuntimeError(f"番号{index}のカメラから映像が取得できません")
    print("【目視確認】CamoのiPhone映像が映っているか確認してください。")
    print("  プレビューを閉じるにはQキーを押してください。")
    try:
        while True:
            width, height = fit_preview_dimensions(image.shape[1], image.shape[0], 1150, 720)
            shown = (cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
                     if (width, height) != (image.shape[1], image.shape[0]) else image)
            cv2.imshow("Camo camera verification - Q to close", shown)
            if (cv2.waitKey(30) & 0xFF) in (ord("q"), ord("Q"), 27):
                break
            ok, new_image = cap.read()
            if not ok or new_image is None:
                raise RuntimeError("プレビュー中にCamoの映像が途切れました")
            image = new_image
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if input("【重要】iPhoneで今撮影している映像で間違いありませんか？ (はい): ").strip() != "はい":
        raise RuntimeError("Camoカメラを未確認のため保存を中止しました")
    return index, image.shape[1], image.shape[0]


def create_profile(index, width, height, backend):
    if not (HERE / "config.json").is_file() and not (HERE / "config.example.json").is_file():
        raise FileNotFoundError("config.json または config.example.json が見つかりません")
    source_config = HERE / "config.json" if (HERE / "config.json").is_file() else HERE / "config.example.json"
    data = json.loads(source_config.read_text(encoding="utf-8-sig"))
    data["facility_id"] = "home-test-001"
    data["camera_id"] = "home-camo-01"
    data["camera_kind"] = "camo"
    data["source"] = index
    data["camera_backend"] = backend
    data["camera_verified_external"] = True
    # 0=デバイスの標準出力を変更しない。Camo側の画角を優先。
    data["camera_capture_width"] = 0
    data["camera_capture_height"] = 0
    data["camera_capture_fps"] = 0
    data["camera_preview_max_width"] = 1280
    data["camera_preview_max_height"] = 800
    data["camera_manual_exposure"] = None
    # 元のUSBカメラ用の座標・メタ情報は、初回Camo登録へ絶対に持ち込まない。
    data.pop("calibration_capture", None)
    data["space_zones"] = {}
    data["entry_zone"] = []
    data["exit_zone"] = []
    data["initially_confirmed_empty_uids"] = []
    data["allow_unverified_initial_empty"] = False
    if PROFILE.exists():
        old = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
        backup = PROFILE.with_name("config_camo_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        shutil.copy2(PROFILE, backup)
        print(f"【バックアップ】{backup.name}")
        # 過去に同じCamoを登録済みでも、取り付け場所やズームの変化を自動判定はできない。
        keep = input("以前とiPhoneの設置位置・向き・ズームは完全に同じですか？ "
                     "「同じ」と入力すると以前の枠を保持（それ以外は再登録）: ").strip() == "同じ"
        if keep and old.get("source") == index and old.get("camera_backend") == backend:
            meta = old.get("calibration_capture") or {}
            if (meta.get("width") and meta.get("height") and
                    abs(width / height - meta["width"] / meta["height"]) <= 0.025):
                for field in ("space_zones", "entry_zone", "exit_zone",
                              "calibration_capture", "initially_confirmed_empty_uids"):
                    data[field] = old.get(field, data.get(field))
                print("【保持】以前の枠を引き継ぎました。現地の映像上で必ず照合してください。")
            else:
                print("【画角変更】解像度・縦横比が異なるため区画の再登録が必要です。")
    # 新規Camoは従来USBの区画位置を引き継がない。
    if not data.get("calibration_capture"):
        data["space_zones"] = {}
        data["entry_zone"] = []
        data["exit_zone"] = []
        data["initially_confirmed_empty_uids"] = []
        data["allow_unverified_initial_empty"] = False
    PROFILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"【保存】{PROFILE}")
    print(f"【出力画角】{width}x{height}、切り抜きなし。Camo側でレンズ・ズームも確認してください。")
    if not data.get("space_zones"):
        print("【次の作業】Camoの映像で駐車区画の四隅を登録してください。")
    else:
        print("【次の作業】登録区画の位置をプレビューで目視確認してください。")
    print("【注意】この段階ではSupabaseには送信していません。")


def main():
    parser = argparse.ArgumentParser(description="Camo用の自宅駐車場設定")
    parser.add_argument("--index", type=int, help="OpenCVカメラ番号（省略すると自動探索）")
    parser.add_argument("--backend", choices=("auto", "msmf", "dshow"), default="auto")
    args = parser.parse_args()
    if args.index is not None and not 0 <= args.index <= 15:
        parser.error("--indexは0〜15で入力してください")
    import cv2
    number, width, height = pick_camera(cv2, args.index, args.backend)
    create_profile(number, width, height, args.backend)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, FileNotFoundError, OSError) as exc:
        raise SystemExit(f"【停止】{exc}") from exc
