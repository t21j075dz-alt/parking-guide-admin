"""Bounded latest camera stills. Public export is opt-in and separately reviewed."""
import base64
from datetime import datetime, timezone
import time


class SnapshotPublisher:
    def __init__(self, writer, config):
        self.writer, self.config = writer, config
        self.last_private = self.last_public = float('-inf')

    def publish(self, frame, now=None):
        if not self.writer or not self.config.get('camera_snapshots_enabled', False):
            return
        import cv2
        now = time.monotonic() if now is None else now
        if now - self.last_private < 5:
            return
        # Failed uploads back off as well; never create an unbounded frame queue.
        self.last_private = now
        self.writer._ensure_token()
        success, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success or jpeg.nbytes > 2_000_000:
            raise ValueError('Camera JPEG must be <= 2 MB; reduce capture resolution')
        row = dict(facility_id=self.config['facility_id'], camera_id=self.config['camera_id'],
                   captured_at=datetime.now(timezone.utc).isoformat(),
                   image_data='data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii'))
        self.writer.upsert('parking_camera_private', [row], 'facility_id,camera_id')
        if self.config.get('public_snapshots_enabled') is not True:
            return
        if now - self.last_public < 300:
            return
        self.last_public = now
        public_frame = frame.copy()
        height, width = public_frame.shape[:2]
        for rectangle in self.config.get('public_snapshot_masks', []):
            if len(rectangle) != 4 or not all(0 <= float(v) <= 1 for v in rectangle):
                raise ValueError('Public snapshot masks require normalized x1,y1,x2,y2')
            x1,y1,x2,y2 = rectangle
            if x1 >= x2 or y1 >= y2:
                raise ValueError('Invalid public mask bounds')
            public_frame[int(y1*height):int(y2*height)+1, int(x1*width):int(x2*width)+1] = 0
        # Public export is lower resolution, never a direct URL to the private still.
        if width > 1280:
            public_frame = cv2.resize(public_frame, (1280, round(height*1280/width)))
        success, jpeg = cv2.imencode('.jpg', public_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            raise ValueError('Cannot encode public snapshot')
        row = dict(row)
        row['image_data'] = 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')
        row['is_published'] = True
        self.writer.upsert('parking_camera_public', [row], 'facility_id,camera_id')
