# -*- coding: utf-8 -*-
"""Conservative low-light enhancement for YOLO inference, not recordings.

The original frame, zone coordinates and source recordings stay unchanged.
CLAHE boosts local contrast but cannot reconstruct motion blur, and may
increase false positives; zone relevance checks still apply.
"""
from __future__ import annotations


def inference_frame(frame, mode="auto"):
    """Return (frame_for_model, applied, sampled_brightness)."""
    if mode == "off" or frame is None:
        return frame, False, None
    import cv2
    import numpy as np

    # Luma is enough for deciding when not to modify daytime video.
    sampled = frame[::8, ::8]
    mean_luma = float(cv2.cvtColor(sampled, cv2.COLOR_BGR2GRAY).mean())
    if mode != "on" and mean_luma >= 58:
        return frame, False, mean_luma

    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(y)
    return cv2.cvtColor(cv2.merge((enhanced, cr, cb)),
                        cv2.COLOR_YCrCb2BGR), True, mean_luma
