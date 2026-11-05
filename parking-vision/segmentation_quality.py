# -*- coding: utf-8 -*-
"""Pure, testable quality presets for optional YOLO instance segmentation.

Never claim that a higher preset guarantees greater accuracy on a particular
camera. Compare predictions against manually annotated ground-truth masks.
Standard exactly preserves the old yolo11n-seg / 640 / low-res-mask setup.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentationSettings:
    quality: str
    model: str
    imgsz: int
    retina_masks: bool


PRESETS = {
    "standard": ("yolo11n-seg.pt", 640, False),
    "high": ("yolo11s-seg.pt", 960, True),
    "maximum": ("yolo11m-seg.pt", 1280, True),
}


def resolve_segmentation_settings(
        quality="auto", *, tracking=False, model=None, imgsz=None):
    """Choose a repeatable setup, preserving explicit CLI overrides.

    Tracking experiments default to High, whereas the older independent
    preview retains its Standard defaults for regression comparisons.
    """
    if quality == "auto":
        quality = "high" if tracking else "standard"
    if quality not in PRESETS:
        raise ValueError("輪郭の品質は auto / standard / high / maximum から選択してください")
    default_model, default_size, retina = PRESETS[quality]
    if imgsz in (None, 0):
        imgsz = default_size
    if not isinstance(imgsz, int) or not 256 <= imgsz <= 1920:
        raise ValueError("輪郭の解析解像度は256～1920の整数を指定してください")
    model = (str(model).strip() if model else "") or default_model
    return SegmentationSettings(quality, model, imgsz, retina)


def infer_segments(model, frame, settings, *, tracking=False,
                   tracker_file=None, confidence=.25):
    """Forward high-resolution mask option to either prediction path.

    Uses one YOLO model inference per frame. The original vehicle detection
    and all occupancy state transitions are outside this function.
    """
    kwargs = {
        "imgsz": settings.imgsz,
        "retina_masks": settings.retina_masks,
        "conf": float(confidence),
        "verbose": False,
    }
    if tracking:
        if not tracker_file:
            raise ValueError("追跡設定ファイルが指定されていません")
        return model.track(frame, persist=True, tracker=tracker_file, **kwargs)
    return model.predict(frame, **kwargs)
