# -*- coding: utf-8 -*-
"""Night camera preprocessing with false-positive safeguards.

Contrast enhancement is deliberately NOT applied to almost-black footage
in automatic mode. Extreme dark images contain little true detail; CLAHE
mainly exaggerates sensor noise, reflections and headlights into patterns
YOLO can mistake for a vehicle. Raw camera recordings are never altered.
"""
from __future__ import annotations


def brightness(frame):
    """Mean luma (0..255) on a subsampled original BGR frame."""
    if frame is None:
        return None
    import cv2
    return float(cv2.cvtColor(frame[::8, ::8], cv2.COLOR_BGR2GRAY).mean())


def is_low_light(frame):
    level = brightness(frame)
    return level is not None and level < 58


def inference_frame(frame, mode="auto"):
    """Return (model_frame, enhanced, mean_luma).

    auto: no enhancement for nearly black (<35) OR normally lit (>=58)
    on: forced CLAHE for a controlled comparison experiment.
    off: raw video only, no enhancement.
    """
    if mode == "off" or frame is None:
        return frame, False, brightness(frame)
    import cv2
    mean_luma = brightness(frame)
    if mode == "auto" and (mean_luma < 35 or mean_luma >= 58):
        return frame, False, mean_luma
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    # Modest local contrast, lower strength than the previous clipLimit=2.0
    # to reduce exaggeration of false car-like objects.
    enhanced = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(8, 8)).apply(y)
    return cv2.cvtColor(cv2.merge((enhanced, cr, cb)),
                        cv2.COLOR_YCrCb2BGR), True, mean_luma
