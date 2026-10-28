"""写真の公開範囲、更新間隔、解像度と保存行の制限。"""
import unittest
from unittest.mock import Mock
import base64
import cv2
import numpy as np
from camera_snapshots import SnapshotPublisher


class SnapshotTests(unittest.TestCase):
    def test_disabled_does_not_publish(self):
        writer=Mock()
        SnapshotPublisher(writer, {}).publish(np.zeros((10,10,3),np.uint8), now=0)
        writer.upsert.assert_not_called()

    def test_private_resolution_and_public_cadence(self):
        writer=Mock()
        publisher=SnapshotPublisher(writer, dict(camera_snapshots_enabled=True,
            public_snapshots_enabled=True, facility_id='f',camera_id='usb',
            public_snapshot_masks=[[0,0,0.5,1]]))
        frame=np.full((720,1600,3),255,np.uint8)
        for now in (0,1,5,295,300): publisher.publish(frame,now)
        calls=writer.upsert.call_args_list
        private=[c.args[1][0] for c in calls if c.args[0]=='parking_camera_private']
        public=[c.args[1][0] for c in calls if c.args[0]=='parking_camera_public']
        self.assertEqual(len(private),4);self.assertEqual(len(public),2)
        decode=lambda r:cv2.imdecode(np.frombuffer(base64.b64decode(r['image_data'].split(',')[1]),np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(decode(private[0]).shape,frame.shape)
        self.assertEqual(decode(public[0]).shape[1],1280)
        self.assertLess(decode(public[0])[0,0].max(),10)
        self.assertTrue((frame==255).all())

    def test_publication_is_explicit_and_failed_private_does_not_export(self):
        writer=Mock()
        pub=SnapshotPublisher(writer,dict(camera_snapshots_enabled=True,facility_id='f',camera_id='c'))
        pub.publish(np.zeros((10,10,3),np.uint8),0)
        self.assertEqual([c.args[0] for c in writer.upsert.call_args_list],['parking_camera_private'])
        writer.upsert.side_effect=OSError('offline')
        with self.assertRaises(OSError):pub.publish(np.zeros((10,10,3),np.uint8),5)
