"""管理者アプリが保存した駐車枠ID/属性をカメラ側の定義と照合する。

管理アプリのx,yは地図上の座標でありカメラ画面のピクセル座標ではない。
必ずcalibrate.pyで対応付けしたspace_uidだけを監視する。
"""
from __future__ import annotations
import json
from pathlib import Path


def extract(layout, facility_id):
    if not isinstance(layout, dict):
        raise ValueError("管理アプリのレイアウトはJSONオブジェクトである必要があります")
    if "objects" not in layout:
        layout = layout.get(facility_id)
    if not isinstance(layout, dict) or layout.get("facilityId") != facility_id:
        raise ValueError(f"施設ID {facility_id} に対応する管理アプリのレイアウトがありません")
    objects = layout.get("objects")
    if not isinstance(objects, list):
        raise ValueError("レイアウトのobjectsが配列ではありません")
    spaces = {}
    for item in objects:
        if not isinstance(item, dict) or item.get("objectType") != "parkingSpace":
            continue
        uid = item.get("uid")
        if not isinstance(uid, str) or not uid or uid in spaces:
            raise ValueError("管理アプリの区画UIDが空欄または重複しています")
        spaces[uid] = {
            "space_number": item.get("spaceNumber") or item.get("name") or uid,
            "space_type": item.get("spaceType") or "standard",
            "label": item.get("name") or "",
        }
    return spaces


def verify(layout, facility_id, camera_uids):
    spaces = extract(layout, facility_id)
    if not spaces:
        raise ValueError("管理アプリ側に駐車区画が登録されていません")
    if not camera_uids:
        raise ValueError("カメラに登録した区画がありません")
    unmatched = sorted(set(camera_uids) - set(spaces))
    if unmatched:
        raise ValueError(
            "カメラの駐車枠IDと管理アプリが一致しません: " + ", ".join(unmatched)
            + "。番号ではなくUIDで対応付けしてください"
        )
    return {uid: spaces[uid] for uid in camera_uids}


def read_export(file_path, facility_id, camera_uids):
    path = Path(file_path)
    if not path.is_file():
        raise ValueError("管理レイアウトのファイルがありません: " + str(path))
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    return verify(obj, facility_id, camera_uids)
