#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USBカメラの露出を調整する。カメラ非対応時は無理に設定を保存しない。

機種によってOpenCVの露出の単位と可否は異なる。
ここではWindows DirectShowでよく使われる-13～0の整数だけを扱う。
見た目の明るさではなく、カメラ側の露出を変更する。
"""
from __future__ import annotations

import math


MIN_EXPOSURE = -13
MAX_EXPOSURE = 0
INITIAL_EXPOSURE = -7


def is_valid_manual_exposure(value):
    """boolはintのサブクラスだが、露出設定として受け付けない。"""
    return type(value) is int and MIN_EXPOSURE <= value <= MAX_EXPOSURE


def set_manual_exposure(camera, cv2, exposure):
    """ドライバの応答と読戻しで実際に反映できたか確認する。

    戻り値がFalseなら設定保存・変更成功の表示をしない。
    カメラが設定値を読戻しできない場合も、安全側に未対応と判断する。
    """
    if not is_valid_manual_exposure(exposure):
        return False
    try:
        camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # 一部のUSB機器では非対応
        if not camera.set(cv2.CAP_PROP_EXPOSURE, float(exposure)):
            return False
        actual = float(camera.get(cv2.CAP_PROP_EXPOSURE))
        return math.isfinite(actual) and abs(actual - exposure) < 0.51
    except (AttributeError, ValueError, TypeError, OSError):
        return False


def step_manual_exposure(camera, cv2, previous, delta):
    """露出を1段暗く/明るく。戻り値は(成功、適用値)。"""
    if delta not in (-1, 1):
        return False, previous
    if is_valid_manual_exposure(previous):
        candidate = max(MIN_EXPOSURE, min(MAX_EXPOSURE, previous + delta))
    else:
        # 露出が未知なら-7を基準に、初回操作の方向に1段動かす。
        candidate = max(MIN_EXPOSURE, min(MAX_EXPOSURE, INITIAL_EXPOSURE + delta))
    if set_manual_exposure(camera, cv2, candidate):
        return True, candidate
    return False, previous
