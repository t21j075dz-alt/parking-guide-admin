"""YOLOの追跡IDをそのまま表示せず、時空間/検出矩形/外観で連続性を検証する。

同時刻の複数車両に同じ番号を振らない。曖昧な対応は無理に接続せず
新しい番号を発行する（見かけのID維持率のために別の車を混同しない）。
画像やナンバープレートは保存しない。
"""
from __future__ import annotations
from dataclasses import dataclass
from math import hypot

FOUR_WHEEL = {"car", "van", "truck", "bus", "vehicle"}
TWO_WHEEL = {"motorcycle", "bicycle", "tricycle", "awning_tricycle"}


def vehicle_group(name):
    if name in FOUR_WHEEL:
        return "four_wheel"
    if name in TWO_WHEEL:
        return "two_wheel"
    return name


def similarity(left, right):
    if left is None or right is None or len(left) != len(right):
        return None
    a = sum(v * v for v in left) ** .5
    b = sum(v * v for v in right) ** .5
    if not a or not b:
        return None
    return sum(x * y for x, y in zip(left, right)) / (a * b)


def appearance_vector(frame, detection):
    """低解像度の色分布。背景を減らし、同じ車の再検出を補助するだけ。"""
    try:
        import cv2
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in detection["bbox"]]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2-x1 < 12 or y2-y1 < 12:
            return None
        dx, dy = (x2-x1)//5, (y2-y1)//5
        patch = frame[y1+dy:y2-dy, x1+dx:x2-dx]
        if patch.size == 0:
            return None
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        return cv2.calcHist([hsv], [0, 1], None, [8, 4],
                            [0, 180, 0, 256]).flatten().astype(float).tolist()
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def box_iou(a, b):
    if a is None or b is None or len(a) != 4 or len(b) != 4:
        return None
    if a[2] <= a[0] or b[2] <= b[0] or a[3] <= a[1] or b[3] <= b[1]:
        return None
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(
        0, min(a[3], b[3])-max(a[1], b[1]))
    aa = (a[2]-a[0])*(a[3]-a[1])
    bb = (b[2]-b[0])*(b[3]-b[1])
    return intersection / max(1.e-9, aa+bb-intersection)


@dataclass
class Remembered:
    stable_id: int
    raw_id: int
    group: str
    point: tuple
    seen: float
    appearance: list | None = None
    bbox: list | None = None


class StableIdMatcher:
    """全検出に対し1対1で割り当てる。重複・入れ替わりを抑制。"""

    def __init__(self, max_missing=12.0):
        self.max_missing = float(max_missing)
        self.next_id = 1
        self.last = {}
        self.raw_to_stable = {}
        self.reassociated = 0
        self.ambiguous = 0
        self.new_tracks = 0

    def _score(self, det, old, now, vector):
        if vehicle_group(det["name"]) != old.group:
            return None
        gap = now - old.seen
        if gap < 0 or gap > self.max_missing:
            return None
        distance = hypot(det["point"][0]-old.point[0], det["point"][1]-old.point[1])
        iou = box_iou(det.get("bbox"), old.bbox)
        # 固定カメラなら同じ車はほぼ同じ位置・検出矩形に現れる。
        # 0.035は画面対角の約3.5%、最大0.14までは時間と共に許す。
        limit = min(0.14, 0.035 + 0.012 * gap)
        is_same_raw = det.get("track_id") == old.raw_id
        if distance > (max(0.12, limit) if is_same_raw else limit):
            return None
        color = similarity(vector, old.appearance)
        if color is not None and color < 0.50:
            return None
        # 実画像では矩形IoUが最も有力。矩形が利用できない時だけ位置で評価。
        if not is_same_raw and iou is not None and iou < 0.08 and distance > 0.015:
            return None
        dist_score = max(0., 1. - distance/max(limit, 0.015))
        color_score = color if color is not None else .45
        iou_score = iou if iou is not None else dist_score
        raw_bonus = 1.3 if is_same_raw else 0.
        return 2.5*iou_score + 1.5*dist_score + .5*color_score + raw_bonus - .1*gap

    def update(self, detections, now, frame=None):
        if not isinstance(now, (float, int)):
            raise TypeError("time must be seconds")
        # 保持期限が切れた記録の生IDも破棄。
        for sid, old in list(self.last.items()):
            if now-old.seen > self.max_missing:
                self.last.pop(sid)
        self.raw_to_stable = {
            old.raw_id: sid for sid, old in self.last.items()
        }

        candidates = []
        observations = []
        for index, det in enumerate(detections):
            record = dict(det)
            raw = record.get("track_id")
            if raw is None:
                observations.append((index, record, None))
                continue
            record["track_id"] = int(raw)
            vec = (appearance_vector(frame, record)
                   if frame is not None else record.get("appearance"))
            observations.append((index, record, vec))
            for sid, old in self.last.items():
                score = self._score(record, old, now, vec)
                if score is not None:
                    candidates.append((score, index, sid))

        # 同時出現する車両に同じIDを振らない。
        # 双方向の曖昧性を評価してから、スコア順に1対1割当て。
        by_det = {}
        by_sid = {}
        for score, index, sid in candidates:
            by_det.setdefault(index, []).append(score)
            by_sid.setdefault(sid, []).append(score)
        for scores in list(by_det.values()) + list(by_sid.values()):
            scores.sort(reverse=True)
        assigned = {}
        occupied = set()
        for score, index, sid in sorted(candidates, key=lambda t: t[0], reverse=True):
            if index in assigned or sid in occupied:
                continue
            det_scores, id_scores = by_det[index], by_sid[sid]
            # 生IDが継続している場合はIoUの強い一致を優先する。
            previous = self.last[sid]
            raw = observations[index][1]["track_id"]
            same_raw = raw == previous.raw_id
            ambiguous_det = len(det_scores) > 1 and det_scores[0]-det_scores[1] < .35
            ambiguous_sid = len(id_scores) > 1 and id_scores[0]-id_scores[1] < .35
            if (ambiguous_det or ambiguous_sid) and not same_raw:
                self.ambiguous += 1
                continue
            assigned[index] = sid
            occupied.add(sid)

        output = []
        for index, record, vec in observations:
            raw = record.get("track_id")
            if raw is None:
                output.append(record)
                continue
            stable = assigned.get(index)
            if stable is None:
                stable = self.next_id
                self.next_id += 1
                self.new_tracks += 1
            elif raw != self.last[stable].raw_id:
                self.reassociated += 1
            prev = self.last.get(stable)
            self.last[stable] = Remembered(
                stable, raw, vehicle_group(record["name"]),
                tuple(record["point"]), float(now),
                vec if vec is not None else (prev.appearance if prev else None),
                record.get("bbox") or (prev.bbox if prev else None),
            )
            record["raw_track_id"] = raw
            record["track_id"] = stable
            output.append(record)
        return output
