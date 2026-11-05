"""管理者アプリの4点位置合わせJSONを既存YOLOカメラ設定へ安全に取り込む。

通常は確認表示のみ。--apply と --confirm-camera-view の両方が揃ったとき
だけバックアップを作って config.json の space_zones を更新する。
カメラ番号・認証・公開設定・録画設定は絶対に変更しない。
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

from zone_geometry import normalize_corners, audit_zones


def read_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("JSONのルートがオブジェクトではありません")
    return data


def checked_alignment(config, alignment, allow_new_camera_view=False):
    if alignment.get("schema_version") != 1:
        raise ValueError("位置合わせJSONの形式が未対応です")
    facility = str(config.get("facility_id") or "")
    camera = str(config.get("camera_id") or "")
    if not facility or alignment.get("facility_id") != facility:
        raise ValueError("施設IDが現在のYOLO設定と一致しません")
    if not camera or alignment.get("camera_id") != camera:
        raise ValueError("カメラIDが現在のYOLO設定と一致しません。正しいカメラの映像で再出力してください")
    uids = alignment.get("space_uids")
    zones = alignment.get("space_zones")
    existing = config.get("space_uids")
    if not isinstance(uids, list) or not uids or len(uids) != len(set(map(str, uids))):
        raise ValueError("位置合わせの区画ID一覧が不正です")
    if not all(isinstance(uid, str) and re.fullmatch(r"space_[A-Za-z0-9_-]+", uid) for uid in uids):
        raise ValueError("区画IDに不正な値があります")
    if not isinstance(zones, dict) or set(zones) != set(uids):
        raise ValueError("区画IDとカメラ座標が対応していません")
    if not isinstance(existing, list) or len(existing) != len(set(existing)) or set(existing) != set(uids):
        raise ValueError("現在のYOLOの監視区画IDと、マップの区画IDが一致しません。勝手に追加・削除しません")
    for field in ("map_points", "image_points"):
        points = alignment.get(field)
        if not isinstance(points, list) or len(points) != 4:
            raise ValueError("対応点はマップ・カメラそれぞれ4点必要です")
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or not all(
                isinstance(v, (float, int)) and not isinstance(v, bool) and 0 <= v <= 1 for v in point
            ):
                raise ValueError("対応点の座標が不正です")
    dimensions = (alignment.get("image_width"), alignment.get("image_height"))
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in dimensions):
        raise ValueError("カメラ画像の幅・高さが不正です")
    capture = config.get("calibration_capture") or {}
    if capture.get("width") and capture.get("height"):
        registered_ratio = float(capture["width"]) / float(capture["height"])
        image_ratio = dimensions[0] / dimensions[1]
        if abs(registered_ratio / image_ratio - 1) > .02 and not allow_new_camera_view:
            raise ValueError("カメラ映像の縦横比が前回の設定と異なります。異なる画角の画像は使用できません")
    validated = {}
    for uid in uids:
        polygon = zones[uid]
        if not isinstance(polygon, list) or len(polygon) != 4:
            raise ValueError(uid + " の四隅がありません")
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                and 0 <= v <= 1 for v in point
            ):
                raise ValueError(uid + " の座標が画像範囲外です")
        # 並び順を正規化。極小枠・自己交差・一直線の枠は拒否する。
        try:
            validated[uid] = normalize_corners(polygon)
        except ValueError as exc:
            raise ValueError(uid + " の四隅が不正です: " + str(exc)) from exc
    warnings = audit_zones(validated)
    if warnings:
        raise ValueError("枠が重複しています。マップ上の位置を確認してください: " + "; ".join(warnings))
    return validated


def validate_verification(config, alignment, verification, alignment_file):
    """最新の実カメラ確認記録と書き出したJSONが同一かを検査する。"""
    if not isinstance(verification, dict) or verification.get("schema_version") != 1:
        raise ValueError("カメラ確認記録の形式が不正です")
    if verification.get("confirmation") != "fixed-camera-live-view-manually-approved":
        raise ValueError("実カメラでの目視確認が記録されていません")
    for key in ("facility_id", "camera_id"):
        if verification.get(key) != config.get(key) or verification.get(key) != alignment.get(key):
            raise ValueError(key + " が実カメラの検証記録と一致しません")
    if (type(verification.get("camera_source")) is not type(config.get("source"))
            or verification.get("camera_source") != config.get("source")):
        raise ValueError("確認時と現在のカメラ入力元が異なります")
    if verification.get("camera_kind") != str(config.get("camera_kind", "usb")).lower():
        raise ValueError("確認時と現在のカメラ種類が異なります")
    if verification.get("space_uids") != alignment.get("space_uids"):
        raise ValueError("確認済みの区画一覧が異なります")
    checksum = hashlib.sha256(Path(alignment_file).read_bytes()).hexdigest()
    if verification.get("alignment_sha256") != checksum:
        raise ValueError("位置合わせJSONが確認後に変更されています。実カメラで再確認してください")
    width, height = verification.get("image_width"), verification.get("image_height")
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError("確認時のカメラ解像度が不正です")
    if abs((width / height) / (alignment["image_width"] / alignment["image_height"]) - 1) > .015:
        raise ValueError("実カメラ確認時の縦横比と位置合わせ画像が異なります")
    try:
        moment = datetime.fromisoformat(verification["checked_at"])
        if moment.tzinfo is None:
            raise ValueError("タイムゾーンなし")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("実カメラ確認日時が不正です") from exc
    age = datetime.now(timezone.utc) - moment.astimezone(timezone.utc)
    if age < -timedelta(minutes=5) or age > timedelta(days=7):
        raise ValueError("実カメラ確認が期限外です。最新の映像で再確認してください")
    return verification


def prepare_settings(config, alignment, verification=None):
    zones = checked_alignment(config, alignment, allow_new_camera_view=verification is not None)
    updated = dict(config)
    updated["space_zones"] = zones
    updated["map_alignment"] = {
        "schema_version": 1,
        "facility_id": alignment["facility_id"],
        "camera_id": alignment["camera_id"],
        "image_width": alignment["image_width"],
        "image_height": alignment["image_height"],
        "map_canvas": alignment.get("map_canvas"),
        "map_points": alignment["map_points"],
        "image_points": alignment["image_points"],
        "source": "administrator-map-four-point",
    }
    if verification:
        # 実カメラで直接確認した画像サイズと入力元を次回起動の画角チェックに利用。
        updated["calibration_capture"] = {
            "width": verification["image_width"],
            "height": verification["image_height"],
            "source": str(config["source"]),
            "kind": str(config.get("camera_kind", "usb")).lower(),
        }
        updated["map_alignment"]["live_verified_at"] = verification["checked_at"]
        updated["map_alignment"]["alignment_sha256"] = verification["alignment_sha256"]
    return updated


def apply_file(config_path, settings):
    config_path = Path(config_path).resolve()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = config_path.with_name("config_backup_map_alignment_" + stamp + ".json")
    shutil.copy2(config_path, backup)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", prefix=".map_alignment_",
            dir=config_path.parent, delete=False
        ) as temp:
            name = temp.name
            json.dump(settings, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
        os.replace(name, config_path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description="管理マップ→カメラの区画座標を安全に取り込む")
    parser.add_argument("--config", default="config.json", help="YOLO側の既存設定")
    parser.add_argument("--alignment", required=True, help="管理者アプリから保存した位置合わせJSON")
    parser.add_argument("--apply", action="store_true", help="バックアップ後に保存")
    parser.add_argument("--confirm-camera-view", action="store_true",
                        help="従来方式の手動確認（既存画角が同じ場合のみ）")
    parser.add_argument("--verification", default="",
                        help="verify_map_alignment.py による実カメラの検証記録JSON")
    args = parser.parse_args(argv)

    settings = read_json(args.config)
    alignment = read_json(args.alignment)
    receipt = None
    if args.verification:
        receipt = validate_verification(settings, alignment,
                                         read_json(args.verification), args.alignment)
    proposed = prepare_settings(settings, alignment, receipt)
    print("施設:", proposed["facility_id"], "/ カメラ:", proposed["camera_id"])
    print("自動生成された監視区画数:", len(proposed["space_zones"]))
    print("対象区画:", ", ".join(proposed["space_uids"]))
    if not args.apply:
        print("【確認のみ】既存のconfig.jsonには書き込んでいません。")
        print("推奨: verify_map_alignment.py で実カメラを確認し、--apply --verification 検証記録.json で反映してください。")
        return 0
    if not receipt and not args.confirm_camera_view:
        parser.error("書込みには --verification 検証記録.json、または --confirm-camera-view が必要です")
    backup = apply_file(args.config, proposed)
    print("【反映済み】YOLO用の space_zones を更新しました。")
    print("【バックアップ】", backup)
    print("YOLOを再起動すると反映されます。クラウドへの送信はここでは行いません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
