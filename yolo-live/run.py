"""YOLOカメラ判定 → Supabase共有。映像・ナンバープレートは送信しない。"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from parking_engine import Detection, ParkingEngine

# 学習済みモデルは各PCに置く。公開GitHubへアップロードしない。
HERE = Path(__file__).resolve().parent


class Remote:
    """Supabase Authのユーザートークンを使い、安全にDBへ書き込む。"""

    def __init__(self, config):
        self.base = config["supabase_url"].rstrip("/")
        self.key = config["publishable_key"]
        self.email = os.environ.get("YOLO_EMAIL") or input("管理者メールアドレス: ").strip()
        self.password = os.environ.get("YOLO_PASSWORD") or getpass.getpass("管理者パスワード: ")
        self.token = ""
        self.refresh_token = ""
        self.expires_at = 0.0
        self.login()

    def request(self, route, method="GET", body=None, authenticated=True, retry=True):
        if authenticated and time.time() > self.expires_at - 60:
            self.refresh()
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        if method == "POST":
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = Request(self.base + route, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=10) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except HTTPError as error:
            if error.code == 401 and authenticated and retry:
                self.refresh()
                return self.request(route, method, body, authenticated, retry=False)
            # トークン・パスワード・応答ボディをログに出さない。
            raise RuntimeError(f"Supabase通信失敗 (HTTP {error.code})") from error
        except URLError as error:
            raise RuntimeError("Supabaseに接続できません。回線を確認してください。") from error

    def login(self):
        reply = self.request("/auth/v1/token?grant_type=password", "POST",
                             {"email": self.email, "password": self.password}, False)
        self._set_session(reply)

    def refresh(self):
        if not self.refresh_token:
            self.login()
            return
        try:
            reply = self.request("/auth/v1/token?grant_type=refresh_token", "POST",
                                 {"refresh_token": self.refresh_token}, False)
            self._set_session(reply)
        except RuntimeError:
            self.login()

    def _set_session(self, result):
        if not result or not result.get("access_token"):
            raise RuntimeError("ログインに失敗しました。管理者アカウントを確認してください。")
        self.token = result["access_token"]
        self.refresh_token = result.get("refresh_token", "")
        self.expires_at = time.time() + int(result.get("expires_in", 3600))

    def validate_slots(self, facility_id, slots):
        key = quote(facility_id, safe="")
        rows = self.request(
            f"/rest/v1/parking_layouts?facility_id=eq.{key}&select=layout_data",
            authenticated=False,
        )
        if not rows:
            raise RuntimeError("施設の登録レイアウトがありません。先に管理画面で保存してください。")
        registered = {item.get("uid") for item in rows[0]["layout_data"]["objects"]
                      if item.get("objectType") == "parkingSpace"}
        missing = set(slots) - registered
        if missing:
            raise RuntimeError("登録されていない区画ID: " + ", ".join(sorted(missing)))

    def send(self, facility_id, camera_id, statuses, journeys):
        if statuses:
            payload = [{**s, "facility_id": facility_id, "source": "yolo"}
                       for s in statuses]
            self.request("/rest/v1/parking_live_status?on_conflict=facility_id,space_uid",
                         "POST", payload)
        if journeys:
            payload = [{**s, "facility_id": facility_id, "camera_id": camera_id}
                       for s in journeys]
            self.request("/rest/v1/parking_vehicle_sessions?on_conflict=session_id",
                         "POST", payload)


def extract(result, width, height, tracked=True):
    """YOLOのboxを画面比率とクラス名に変換。欠けた追跡IDはNone。"""
    detections = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections
    ids = boxes.id.int().cpu().tolist() if tracked and boxes.id is not None else []
    for i, box in enumerate(boxes):
        xyxy = box.xyxy[0].cpu().tolist()
        point = ((xyxy[0] + xyxy[2]) / (2 * width), xyxy[3] / height)
        label = str(result.names[int(box.cls.item())])
        detections.append(Detection(
            label=label, point=point, confidence=float(box.conf.item()),
            track_id=ids[i] if i < len(ids) else None,
        ))
    return detections


def main():
    parser = argparse.ArgumentParser(description="駐車場カメラの自動判定と共有")
    parser.add_argument("--config", default=str(HERE / "camera-config.json"), help="カメラ設定JSON")
    parser.add_argument("--source", default=None, help="0=Webカメラ、動画パス、RTSP URL")
    parser.add_argument("--preview", action="store_true", help="認識結果を画面に表示（Qで終了）")
    args = parser.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if not cfg.get("slots"):
        raise SystemExit("区画が未設定です。先に calibrate.py でカメラ上の区画を指定してください。")
    for uid, points in cfg["slots"].items():
        if len(points) < 3 or any(len(p) != 2 or not all(0 <= float(v) <= 1 for v in p) for p in points):
            raise SystemExit(f"{uid}: 区画の頂点は画像内0〜1の比率座標で3点以上必要です。")
    remote = Remote(cfg)
    remote.validate_slots(cfg["facility_id"], cfg["slots"])
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as error:
        raise SystemExit("必要なライブラリがありません。pip install -r requirements.txt を実行してください。") from error

    detector = YOLO(cfg["vehicle_model"])
    detected_labels = {str(v).lower() for v in detector.names.values()}
    if not detected_labels.intersection({"car", "van", "truck", "bus", "motor", "motorcycle"}):
        raise SystemExit("車両クラスがモデルに含まれていません。学習済みbest.ptを指定してください。")

    obstacle_path = str(cfg.get("obstacle_model", "")).strip()
    obstacle_detector = YOLO(obstacle_path) if obstacle_path else None
    if obstacle_detector:
        obstacles = {str(v).lower().strip() for v in obstacle_detector.names.values()}
        if not obstacles.intersection({"traffic cone", "traffic_cone", "cone", "shopping cart",
                                      "shopping_cart", "cart", "trolley", "barrier", "bollard", "obstacle"}):
            raise SystemExit("障害物モデルのクラス名が未対応です。設定と学習時の名前を確認してください。")
    elif cfg.get("require_obstacle_detection", True):
        print("注意：障害物モデル未設定のため、空き区画は「未確認」として送信します。")

    engine = ParkingEngine(cfg)
    source = args.source if args.source is not None else cfg.get("source", 0)
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    def open_capture():
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError("カメラ/動画を開けません。sourceを確認してください。")
        return cap

    cap = open_capture()
    camera_id, facility_id = cfg["camera_id"], cfg["facility_id"]
    print(f"判定開始: {facility_id} / {camera_id} / {len(engine.slots)}区画")
    print("送信するのは区画状態と匿名の車両IDのみです。カメラ映像は送信しません。")
    is_file = isinstance(source, str) and not source.lower().startswith(("rtsp:", "http:","https:"))
    read_failures = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                read_failures += 1
                if read_failures == 1:
                    try:
                        remote.send(facility_id, camera_id, engine.offline_states(), [])
                    except RuntimeError as error:
                        print(error)
                if is_file:
                    print("動画を最後まで解析しました。")
                    break
                cap.release()
                time.sleep(3)
                try:
                    cap = open_capture()
                    read_failures = 0
                    # 映像が切り替わった可能性があるので追跡IDを引き継がない。
                    engine = ParkingEngine(cfg)
                    detector = YOLO(cfg["vehicle_model"])
                except RuntimeError as error:
                    print(error)
                continue

            read_failures = 0
            height, width = frame.shape[:2]
            result = detector.track(frame, persist=True, tracker="bytetrack.yaml",
                                    conf=0.20, verbose=False)[0]
            things = extract(result, width, height)
            if obstacle_detector:
                obstacle_result = obstacle_detector.predict(frame, conf=0.25, verbose=False)[0]
                things.extend(extract(obstacle_result, width, height, tracked=False))

            statuses, journeys = engine.update(
                things, datetime.now(timezone.utc), obstacle_model_ready=bool(obstacle_detector),
            )
            if statuses or journeys:
                try:
                    remote.send(facility_id, camera_id, statuses, journeys)
                    if statuses:
                        visible = " ".join(f"{s['space_uid']}={s['status']}" for s in statuses)
                        print(datetime.now().strftime("%H:%M:%S"), visible)
                except RuntimeError as error:
                    print("送信できませんでした（次回再試行）:", error)

            if args.preview:
                view = result.plot()
                cv2.putText(view, f"Camera: {camera_id}  Spaces: {len(engine.slots)}",
                            (16, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.imshow("Parking YOLO - Q to stop", view)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    except KeyboardInterrupt:
        print("手動で停止しました。")
    finally:
        try:
            remote.send(facility_id, camera_id, engine.offline_states(), [])
        except RuntimeError:
            print("停止情報を送信できません。15秒経過した状態はアプリ側で未確認扱いにしてください。")
        cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        print("終了しました。")


if __name__ == "__main__":
    main()
