"""YOLOの追跡番号が変化しても、カメラ内の一時的な車両番号を安定化する。

一度見失っても近くに現れた同種の車を再対応付けする。ただし確実な
車両認証ではない。似た車・長い死角・画角外移動は保証しない。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

FOUR_WHEEL = {"car", "van", "truck", "bus", "vehicle"}
TWO_WHEEL = {"motorcycle", "bicycle", "tricycle", "awning_tricycle"}


def vehicle_group(name: str) -> str:
    if name in FOUR_WHEEL:
        return "four_wheel"
    if name in TWO_WHEEL:
        return "two_wheel"
    return name


def similarity(left: list[float] | None, right: list[float] | None) -> float | None:
    """画像由来の色分布ベクトルの類似度（ない場合はNone）。"""
    if left is None or right is None or len(left) != len(right):
        return None
    a = sum(v * v for v in left) ** 0.5
    b = sum(v * v for v in right) ** 0.5
    if a <= 0 or b <= 0:
        return None
    return sum(x * y for x, y in zip(left, right)) / (a * b)


def appearance_vector(frame, detection) -> list[float] | None:
    """車の塗装の色分布のみ利用。ナンバープレート・顔識別はしない。"""
    try:
        import cv2
        x1, y1, x2, y2 = [int(v) for v in detection["bbox"]]
        h, w = frame.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 - x1 < 12 or y2 - y1 < 12:
            return None
        # 境界の背景の影響を下げるため画像中央60%を使用
        pad_x = (x2 - x1) // 5
        pad_y = (y2 - y1) // 5
        patch = frame[y1 + pad_y:y2 - pad_y, x1 + pad_x:x2 - pad_x]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256])
        flat = hist.flatten().astype(float).tolist()
        return flat
    except (KeyError, ValueError, TypeError):
        return None


@dataclass
class Remembered:
    stable_id: int
    raw_id: int
    group: str
    point: tuple[float, float]
    seen: float
    appearance: list[float] | None = None


class StableIdMatcher:
    """未検出の間はIDを短時間保持し、誤結合が不安な場合は新IDを発行する。"""

    def __init__(self, max_missing: float = 12.0):
        self.max_missing = max_missing
        self.next_id = 1
        self.last: dict[int, Remembered] = {}
        self.raw_to_stable: dict[int, int] = {}
        self.reassociated = 0

    def update(self, detections: list[dict], now: float, frame=None) -> list[dict]:
        # 過去のIDを無期限に再使用しない（別の車を同一とみなさない）。
        for stable_id, seen in list(self.last.items()):
            if now - seen.seen > self.max_missing:
                del self.last[stable_id]
                if self.raw_to_stable.get(seen.raw_id) == stable_id:
                    del self.raw_to_stable[seen.raw_id]

        current_raw = {
            int(d["track_id"]) for d in detections if d.get("track_id") is not None
        }
        result = []
        reserved: set[int] = set()
        # 最初に同じ生IDを優先確保し、別の車に再使用しない。
        for det in detections:
            raw = det.get("track_id")
            if raw is None:
                result.append(dict(det))
                continue
            raw = int(raw)
            stable = self.raw_to_stable.get(raw)
            if stable is None or stable not in self.last:
                continue
            remembered = self.last[stable]
            distance = hypot(
                det["point"][0] - remembered.point[0],
                det["point"][1] - remembered.point[1],
            )
            if vehicle_group(det["name"]) != remembered.group or distance > 0.45:
                # 生IDの再使用や不自然な座標飛躍は新しい車と見なす。
                del self.raw_to_stable[raw]
                continue
            reserved.add(stable)

        processed = set()
        for det in detections:
            updated = dict(det)
            raw = updated.get("track_id")
            if raw is None:
                result.append(updated)
                continue
            raw = int(raw)
            group = vehicle_group(updated["name"])
            point = tuple(updated["point"])
            vector = appearance_vector(frame, updated) if frame is not None else updated.get("appearance")
            stable = self.raw_to_stable.get(raw)
            if stable not in self.last or stable in processed:
                stable = None

            if stable is None:
                candidates = []
                for candidate_id, last in self.last.items():
                    if candidate_id in reserved or candidate_id in processed:
                        continue
                    if last.group != group or now - last.seen < 0 or now - last.seen > self.max_missing:
                        continue
                    # 時間が経つほど移動できる範囲を広く取るが、
                    # 色分布があるときは一致しない候補を避ける。
                    seconds = now - last.seen
                    distance = hypot(point[0]-last.point[0], point[1]-last.point[1])
                    limit = min(0.45, 0.08 + 0.035 * seconds)
                    if distance > limit:
                        continue
                    color = similarity(vector, last.appearance)
                    if color is not None and color < 0.55:
                        continue
                    candidates.append((distance / max(0.02, limit) +
                                       (1 - color if color is not None else 0.35),
                                       candidate_id, distance))
                candidates.sort()
                # 次点がほぼ同じなら、誤った同一車判定より新IDを選ぶ。
                if candidates and (len(candidates) == 1 or candidates[1][0] - candidates[0][0] > 0.4):
                    stable = candidates[0][1]
                    self.reassociated += 1
                    previous_raw = self.last[stable].raw_id
                    if self.raw_to_stable.get(previous_raw) == stable:
                        del self.raw_to_stable[previous_raw]
                else:
                    stable = self.next_id
                    self.next_id += 1

            self.raw_to_stable[raw] = stable
            self.last[stable] = Remembered(
                stable_id=stable, raw_id=raw, group=group,
                point=point, seen=now, appearance=vector or (
                    self.last.get(stable).appearance if stable in self.last else None
                ),
            )
            processed.add(stable)
            updated["raw_track_id"] = raw
            updated["track_id"] = stable
            result.append(updated)
        return result
