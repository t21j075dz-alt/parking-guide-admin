#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""カメラの実際の縦横比を維持し、古い区画設定の誤使用を防ぐ。"""

def fit_preview_dimensions(width, height, max_width=1280, max_height=800):
    """切り抜かず、縦横比を変えず、表示できる大きさへ縮小する。"""
    if min(width, height, max_width, max_height) <= 0:
        raise ValueError("映像・プレビューの幅と高さは正の値にしてください")
    ratio = min(1.0, max_width / width, max_height / height)
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def capture_preferences(settings):
    """0,0ならカメラ標準の画角・解像度を優先する。"""
    w = int(settings.get("camera_capture_width", 0) or 0)
    h = int(settings.get("camera_capture_height", 0) or 0)
    fps = int(settings.get("camera_capture_fps", 0) or 0)
    if (w == 0) != (h == 0):
        raise ValueError("解像度を指定する場合は幅と高さを両方指定してください")
    if w < 0 or h < 0 or w > 7680 or h > 4320 or fps < 0 or fps > 120:
        raise ValueError("camera_capture_width/height/fps の設定値を確認してください")
    return w, h, fps


def assert_calibrated_view(settings, width, height):
    """別の画角の区画座標を流用しない。旧USB設定だけは従来互換にする。"""
    meta = settings.get("calibration_capture")
    kind = str(settings.get("camera_kind", "usb")).lower()
    if not meta:
        if kind == "camo":
            raise ValueError(
                "Camo映像の区画位置は未検証です。config_camo.jsonでcalibrate.pyを実行してください"
            )
        print("【区画確認】旧設定のため画角の一致を自動確認できません。"
              "撮影位置が変わっていたら駐車枠を再登録してください。")
        return
    if str(meta.get("source")) != str(settings.get("source")):
        raise ValueError("区画登録時とカメラ番号が異なります。区画を再登録してください")
    if str(meta.get("kind", "usb")) != kind:
        raise ValueError("区画登録時とカメラ種類が異なります。区画を再登録してください")
    old_w, old_h = int(meta.get("width", 0)), int(meta.get("height", 0))
    if min(old_w, old_h, width, height) <= 0:
        raise ValueError("区画登録時または現在のカメラ解像度が不正です")
    # 解像度が違っても同じ縦横比なら正規化座標は再利用できる。
    if abs(width / height - old_w / old_h) > 0.025:
        raise ValueError(
            f"画角が変化しました（登録時{old_w}x{old_h}、現在{width}x{height}）。"
            "誤った空車案内を防ぐため、駐車枠を再登録してください"
        )
