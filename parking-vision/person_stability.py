# -*- coding: utf-8 -*-
"""人の追跡IDを増殖させないための、軽量な表示用ID安定化。

人と車は別の追跡対象。車の駐車セッションに人のIDを混ぜない。
YOLOの生IDは画面にそのまま出さず、同じ人物の位置が継続して
確認された場合だけ管理番号を表示する。

- 初めての検出 / 一瞬の誤検出には番号を表示しない。
- 向きや枠サイズが変わっても、近い位置に継続する人の番号を維持。
- 異なる2人が同時に見えている場合、同じ番号を割り当てない。
- カメラで本人確認は行わない。画像・顔は保存しない。
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot


@dataclass
class PersonTrack:
    stable_id: int
    point: tuple[float, float]
    bbox: tuple
    last_seen: float
    first_seen: float
    observations: int
    raw_id: int | None


class PersonIdStabilizer:
    def __init__(self, visible_seconds=1.0, missing_seconds=7.0):
        self.visible_seconds = float(visible_seconds)
        self.missing_seconds = float(missing_seconds)
        self.tracks = {}
        self.next_id = 1

    def update(self, blockers, now):
        """Update the supplied detections in place, returning the same list."""
        now = float(now)
        for sid, item in list(self.tracks.items()):
            if now - item.last_seen > self.missing_seconds:
                del self.tracks[sid]

        candidates = []
        people = []
        for index, det in enumerate(blockers):
            if det.get("name") != "person":
                # Cones and carts do not have stable human IDs.
                det["track_id"] = None
                continue
            raw = det.get("track_id")
            det["raw_person_track_id"] = raw
            det["track_id"] = None
            det["person_confirmed"] = False
            if float(det.get("confidence", 0)) < .42:
                continue
            bbox = det.get("bbox")
            point = det.get("point")
            if not bbox or len(bbox) != 4 or point is None:
                continue
            people.append((index, det, raw))
            for sid, saved in self.tracks.items():
                gap = now - saved.last_seen
                if gap < 0 or gap > self.missing_seconds:
                    continue
                distance = hypot(point[0]-saved.point[0], point[1]-saved.point[1])
                same_raw = raw is not None and raw == saved.raw_id
                # Most people in a parking-camera image are slow and small,
                # but a walking person may move much farther over 2s.
                limit = min(.17, .04 + gap*.055)
                if distance > limit:
                    continue
                a = bbox
                b = saved.bbox
                intersection = (max(0, min(a[2],b[2])-max(a[0],b[0])) *
                                max(0, min(a[3],b[3])-max(a[1],b[1])))
                area_a = max(0,(a[2]-a[0])*(a[3]-a[1]))
                area_b = max(0,(b[2]-b[0])*(b[3]-b[1]))
                iou = intersection / max(1.,area_a+area_b-intersection)
                score = (3.0 * iou + 1.5 * (1.0-distance/max(limit,.001))
                         + (1.0 if same_raw else 0))
                if iou < .03 and distance > .035 and not same_raw:
                    continue
                candidates.append((score, index, sid))

        # Greedy one-to-one, with an ambiguity guard. Never give two visible
        # people one ID in the same frame.
        rankings = {}
        for score, index, sid in candidates:
            rankings.setdefault(index, []).append(score)
        accepted = {}
        used = set()
        for score, index, sid in sorted(candidates, reverse=True):
            if index in accepted or sid in used:
                continue
            scores = sorted(rankings[index], reverse=True)
            if len(scores) > 1 and scores[0]-scores[1] < .25:
                continue
            accepted[index] = sid
            used.add(sid)

        for index, det, raw in people:
            sid = accepted.get(index)
            previous = self.tracks.get(sid)
            if previous is None:
                sid = self.next_id
                self.next_id += 1
                item = PersonTrack(
                    stable_id=sid, point=tuple(det["point"]),
                    bbox=tuple(det["bbox"]), last_seen=now,
                    first_seen=now, observations=1, raw_id=raw)
            else:
                # A single long gap is not uninterrupted evidence of a
                # pedestrian. Confirm again instead of showing stale IDs.
                gap = now - previous.last_seen
                if gap > 2.5:
                    first_seen, observations = now, 1
                else:
                    first_seen = previous.first_seen
                    observations = previous.observations + 1
                item = PersonTrack(sid, tuple(det["point"]),
                                   tuple(det["bbox"]), now, first_seen,
                                   observations, raw)
            self.tracks[sid] = item
            if item.observations >= 3 and now-item.first_seen >= self.visible_seconds:
                det["track_id"] = sid
                det["person_confirmed"] = True
        return blockers
