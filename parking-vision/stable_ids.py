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
    # 最後の2回の観測に基づく画面上の移動速度（正規化座標/秒）
    velocity: tuple = (0.0, 0.0)


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

    def _score(self, det, old, now, vector, isolated=False):
        """Associations survive rotating car boxes, but never teleport cars.

        Same raw ID is useful evidence only while geometry is plausible.
        For a *single* active car after a tracker ID reset, permit a larger
        rotation/translation if its color is a strong independent match.
        Crowded scenes never use this relaxed one-car rule.
        """
        if vehicle_group(det["name"]) != old.group:
            return None
        gap = float(now) - old.seen
        if gap < 0 or gap > self.max_missing:
            return None
        distance = hypot(det["point"][0]-old.point[0], det["point"][1]-old.point[1])
        iou = box_iou(det.get("bbox"), old.bbox)
        limit = min(.16, .042 + .018 * gap)
        is_same_raw = det.get("track_id") == old.raw_id
        color = similarity(vector, old.appearance)
        # If the same raw YOLO ID reappears after a brief blind spot,
        # keep it even when old phantom stable tracks remain in memory.
        # Only an unambiguous raw owner with no other *visible* vehicle
        # qualifies. A tracker may recycle raw IDs after long gaps, hence
        # the strict 9-second bound and spatial plausibility check.
        same_raw_turn = (
            old.group == "four_wheel" and is_same_raw
            and 1.0 <= gap <= 9.0 and distance <= .45
            and self._single_detection_now
        )
        # The car can expose a very different frontal/side area; do not
        # reject a credible same-raw turn based on fragile HSV histograms.
        # Keep strict colour rejection when multiple cars coexist.
        # In a one-car short turn a different camera angle can reduce
        # colour similarity slightly below the standard 0.47 threshold.
        short_single_turn_colour = (
            isolated and not is_same_raw and 1.0 <= gap <= 3.5
            and color is not None and color >= .43
        )
        if (color is not None and color < .47
                and not same_raw_turn and not short_single_turn_colour):
            return None
        # A new raw ID can also follow an abrupt turn. Only reconnect a
        # *single* car after 1–3.5s, with modest visual similarity.
        # Never relax proximity in a multi-car scene.
        # Abrupt YOLO bbox expansion when a car turns can assign raw 42
        # only 0.1-0.8 seconds after raw 1. The previous >=1-second
        # requirement silently rejected this real-world turn even with
        # strong matching colour (around 0.73 in the supplied footage).
        # Short-gap association requires a *single plausible vehicle*,
        # strong appearance, spatial proximity and no competing owner.
        very_short_turn = (
            isolated and old.group == "four_wheel"
            and not is_same_raw and color is not None
            and 0 <= gap < 1.0 and color >= .70 and distance <= .43
        )
        strong_reid = (
            isolated and old.group == "four_wheel"
            and not is_same_raw and color is not None
            and ((color >= .43 and 1.0 <= gap <= 3.5)
                 or (color >= .78 and 3.5 < gap <= 6.5))
            and distance <= min(.43, .09 + .145 * gap)
        ) or very_short_turn
        predicted = (old.point[0] + old.velocity[0]*gap,
                     old.point[1] + old.velocity[1]*gap)
        prediction_distance = hypot(
            det["point"][0]-predicted[0], det["point"][1]-predicted[1]
        )
        # Only trust velocity prediction if it meaningfully improves on the
        # last position; a stationary car may suddenly begin reversing.
        moving_prediction = (
            gap <= 4.0 and hypot(*old.velocity) >= .005
            and prediction_distance < distance * .72
            and prediction_distance <= .14 + .035 * gap
        )
        if distance > (max(.12, limit) if is_same_raw else limit):
            if not strong_reid and not same_raw_turn and not moving_prediction:
                return None

        if (not is_same_raw and iou is not None and iou < .08
                and distance > .015 and not strong_reid
                and not moving_prediction):
            return None
        dist_score = max(0., 1. - distance/max(limit, .015))
        color_score = color if color is not None else .45
        iou_score = iou if iou is not None else dist_score
        raw_bonus = 1.3 if is_same_raw else 0.
        predicted_bonus = .8 if moving_prediction else 0.
        color_bonus = .9 if (strong_reid or same_raw_turn) else 0.
        return (2.5*iou_score + 1.5*dist_score + .5*color_score
                + raw_bonus + predicted_bonus + color_bonus - .1*gap)

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
        # Relaxed long-distance ReID is permissible only for an actual
        # single-car scene; prevent mixing adjacent occupied stalls.
        # Count all identities still inside the actual retention window.
        # Two disappeared cars must never be merged into one on a turn,
        # even if neither was seen in the most recent 3 seconds.
        self._single_detection_now = len(detections) == 1
        # A turning vehicle may coexist with a stale (unseen) phantom
        # remembered track. Relax new-raw ReID only if one recently seen
        # car exists, with all other tracks truly stale (> 6.5 seconds).
        recent = [old for old in self.last.values() if 0 <= now-old.seen <= 3.5]
        others_old = all(
            (now - old.seen > 6.5) for old in self.last.values()
            if old not in recent
        )
        isolated = (
            self._single_detection_now and
            (len(self.last) == 1 or (len(recent) == 1 and others_old))
        )
        # A stale false-positive identity can prevent a legitimate raw-ID
        # handoff even when only one *physical* car is present. Instead of
        # relaxing all matches, select a uniquely plausible recent track:
        # two or more plausible cars must never be merged.
        def exclusive_turn_match(record, vector):
            if not self._single_detection_now or record.get("track_id") is None:
                return None
            target = int(record["track_id"])
            eligible = []
            for sid, old in self.last.items():
                gap = now - old.seen
                if old.group != vehicle_group(record["name"]) or old.raw_id == target:
                    continue
                if not (0 <= gap <= 3.5):
                    continue
                distance = hypot(record["point"][0]-old.point[0],
                                 record["point"][1]-old.point[1])
                distance_limit = (.43 if gap < 1.0
                                  else min(.43, .09 + .145 * gap))
                if distance > distance_limit:
                    continue
                color = similarity(vector, old.appearance)
                minimum_color = .70 if gap < 1.0 else .60
                if color is None or color < minimum_color:
                    continue
                eligible.append(sid)
            return eligible[0] if len(eligible) == 1 else None
        for index, det in enumerate(detections):
            record = dict(det)
            raw = record.get("track_id")
            if raw is not None:
                record["track_id"] = int(raw)
            vec = (appearance_vector(frame, record)
                   if frame is not None else record.get("appearance"))
            observations.append((index, record, vec))
            # Prefer a unique existing owner of the identical raw YOLO
            # ID, even when other stale ID records remain in memory.
            raw_owners = [
                sid for sid, old in self.last.items()
                if raw is not None and old.raw_id == int(raw)
            ]
            unique_turn_sid = exclusive_turn_match(record, vec)
            for sid, old in self.last.items():
                if len(raw_owners) == 1 and sid != raw_owners[0]:
                    # Only enforce ownership preference when that owner's
                    # position is still plausible, to avoid tracking an ID
                    # recycled across widely separated cars.
                    owner = self.last[raw_owners[0]]
                    own_distance = hypot(
                        record["point"][0]-owner.point[0],
                        record["point"][1]-owner.point[1]
                    )
                    if 0 <= now-owner.seen <= 9.0 and own_distance <= .45:
                        continue
                score = self._score(
                    record, old, now, vec,
                    isolated=isolated or sid == unique_turn_sid
                )
                if (score is not None and
                        (raw is not None or
                         (now - old.seen <= 2.5 and score >= 1.3))):
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
            stable = assigned.get(index)
            if stable is None and raw is None:
                # A YOLO detection without a tracker ID may be displayed,
                # but do not invent a new vehicle session for it.
                output.append(record)
                continue
            if stable is None:
                # The latest diagnostic had one isolated false/weak car
                # (raw 16, confidence 0.41) which needlessly consumed a
                # stable display number. Keep the low-confidence detection
                # for diagnostics, but allocate an ID only once it has
                # sufficient evidence. Already matched existing tracks
                # may still survive temporary confidence dips.
                confidence = record.get("confidence")
                if confidence is not None and float(confidence) < .50:
                    record["raw_track_id"] = raw
                    record["id_reassociated"] = False
                    record["track_id"] = None
                    output.append(record)
                    continue
                stable = self.next_id
                self.next_id += 1
                self.new_tracks += 1
            previous_raw = self.last[stable].raw_id if stable in self.last else None
            reassociated = stable in self.last and raw is not None and raw != previous_raw
            if reassociated:
                self.reassociated += 1
            prev = self.last.get(stable)
            velocity = (0., 0.)
            if prev is not None:
                dt = float(now)-prev.seen
                if .15 <= dt <= 4.:
                    current = tuple(record["point"])
                    velocity = ((current[0]-prev.point[0])/dt,
                                (current[1]-prev.point[1])/dt)
                    # Smooth fast turn/jitter, especially large changes in
                    # the YOLO bounding box as the car rotates.
                    velocity = (.65*velocity[0]+.35*prev.velocity[0],
                                .65*velocity[1]+.35*prev.velocity[1])
                else:
                    velocity = prev.velocity
            self.last[stable] = Remembered(
                stable, raw if raw is not None else previous_raw,
                vehicle_group(record["name"]),
                tuple(record["point"]), float(now),
                vec if vec is not None else (prev.appearance if prev else None),
                record.get("bbox") or (prev.bbox if prev else None),
                velocity,
            )
            record["raw_track_id"] = raw
            record["id_reassociated"] = reassociated
            record["track_id"] = stable
            output.append(record)
        return output
