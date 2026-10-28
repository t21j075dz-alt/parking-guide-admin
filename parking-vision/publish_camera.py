"""USB camera photo publishing without a YOLO model or parking-space calibration."""
import argparse
from getpass import getpass
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError

from camera_recording import open_camera
from camera_snapshots import SnapshotPublisher
from monitor import SupabaseWriter


def settings(camera, facility, public=False):
    """Read only the app's public project settings; never create a local password file."""
    source = (Path(__file__).resolve().parent.parent / "sync-config.js").read_text(encoding="utf-8-sig")
    def field(name):
        found = re.search(r'\b' + name + r'\s*:\s*"([^"\r\n]+)"', source)
        if not found:
            raise ValueError(f"sync-config.js: {name} is missing")
        return found.group(1)
    url, key = field("supabaseUrl"), field("publishableKey")
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co', url):
        raise ValueError("Expected the configured Supabase project HTTPS URL")
    if not facility.strip() or len(facility) > 100 or camera < 0:
        raise ValueError("Invalid facility ID or camera number")
    return dict(facility_id=facility, camera_id=f"usb-camera-{camera}",
                supabase_url=url, publishable_key=key,
                camera_snapshots_enabled=True, public_snapshots_enabled=public)


def confirm_camera(cv2, camera):
    """Nothing is sent before the user confirms the actual camera view."""
    print("USBカメラの映像を確認してください。Yで配信へ進む／Q・Escで中止。")
    while True:
        success, frame = camera.read()
        if not success:
            raise ValueError("カメラから映像を取得できません")
        cv2.imshow("Confirm USB camera: Y = continue / Q = quit", frame)
        key = cv2.waitKey(30) & 0xff
        if key in (ord("y"), ord("Y")):
            return
        if key in (ord("q"), ord("Q"), 27):
            raise ValueError("中止しました。写真は送信していません")


def main():
    parser = argparse.ArgumentParser(description="USBカメラ写真を管理アプリへ配信（YOLO不要）")
    parser.add_argument("--camera", type=int, required=True, help="USBカメラ番号。実映像で確認してください")
    parser.add_argument("--facility", default="home-test-001", help="管理アプリで選ぶ施設ID")
    parser.add_argument("--email", default="", help="管理アプリのログイン用メールアドレス")
    parser.add_argument("--public", action="store_true", help="利用者向けにも5分ごとの写真を公開")
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    args = parser.parse_args()
    config = settings(args.camera, args.facility, args.public)
    if ((args.width == 0) != (args.height == 0) or min(args.width, args.height) < 0
            or args.width > 7680 or args.height > 4320):
        parser.error("幅・高さは両方指定してください（0/0はカメラ既定値）")
    import cv2
    camera = open_camera(cv2, args.camera, "auto", None, args.width, args.height, 0)
    try:
        if not camera.isOpened():
            raise ValueError("カメラを開けません。使用中のアプリを閉じ、別のカメラ番号を試してください")
        print(f"施設: {args.facility} / カメラ: {args.camera}")
        print("管理者向け写真: 5秒ごと / 利用者向け写真: " + ("5分ごとに公開" if args.public else "公開しない"))
        print("空き状況の判定・更新は行いません。終了はカメラ画面でQ、またはCtrl+C。")
        confirm_camera(cv2, camera)
        email = args.email or input("管理アプリのメールアドレス: ").strip()
        writer = SupabaseWriter(config["supabase_url"], config["publishable_key"], email,
                                getpass("管理アプリのパスワード（表示・保存されません）: "))
        publisher = SnapshotPublisher(writer, config)
        print("ログイン成功。写真配信を開始します。")
        while True:
            success, frame = camera.read()
            if not success:
                raise ValueError("カメラが切断されました。配信を終了します")
            before = publisher.last_private
            try:
                publisher.publish(frame)
                if publisher.last_private != before:
                    print(time.strftime("%H:%M:%S") + f" 写真送信成功 {frame.shape[1]}×{frame.shape[0]}")
            except (URLError, OSError, ValueError, KeyError) as exc:
                print("写真送信失敗: " + (f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__) + "（接続・権限・JPEGの2MB上限を確認してください）")
            cv2.imshow("USB camera publisher: Q = stop", frame)
            if cv2.waitKey(20) & 0xff in (ord("q"), ord("Q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("写真配信を終了しました。")
    except (ValueError, URLError, OSError, KeyError) as exc:
        print("開始できません: " + (str(exc) if isinstance(exc, ValueError) else f"HTTP {exc.code}" if isinstance(exc, HTTPError) else type(exc).__name__))
        raise SystemExit(1)
