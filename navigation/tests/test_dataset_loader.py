"""
Unit Tests for Dataset Adapters (dataset_loader.py).
"""

import unittest
import os
import tempfile
import numpy as np

from navigation.utils.mock_generator import MockDataGenerator
from navigation.utils.dataset_loader import (
    BlenderDatasetLoader,
    EuRoCDatasetLoader,
    GenericDatasetLoader
)


class TestDatasetLoader(unittest.TestCase):

    def test_blender_dataset_loader(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Export synthetic data
            gen = MockDataGenerator(trajectory_type="circular", duration=1.0, imu_hz=100, camera_hz=30)
            gen.export_dataset_to_disk(tmp_dir)

            # 2. Parse using BlenderDatasetLoader
            loader = BlenderDatasetLoader(tmp_dir)

            imu_count = 0
            cam_count = 0
            sample_frame = None

            for sensor_type, packet in loader.stream_dataset():
                if sensor_type == "imu":
                    imu_count += 1
                    self.assertIn("accel", packet)
                    self.assertIn("gyro", packet)
                    self.assertIn("frame_id", packet)
                elif sensor_type == "camera":
                    cam_count += 1
                    self.assertIn("frame", packet)
                    self.assertIn("frame_id", packet)
                    if sample_frame is None:
                        sample_frame = packet["frame"]

            self.assertGreaterEqual(imu_count, 95)
            self.assertGreaterEqual(cam_count, 28)
            self.assertIsNotNone(sample_frame)
            self.assertEqual(sample_frame.shape, (720, 1280, 3))

    def test_generic_csv_loader(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            gen = MockDataGenerator(trajectory_type="straight_line", duration=0.5, imu_hz=100, camera_hz=30)
            gen.export_dataset_to_disk(tmp_dir)

            loader = GenericDatasetLoader(tmp_dir)
            imu_packets = []
            cam_packets = []

            for sensor_type, packet in loader.stream_dataset():
                if sensor_type == "imu":
                    imu_packets.append(packet)
                elif sensor_type == "camera":
                    cam_packets.append(packet)

            self.assertGreater(len(imu_packets), 45)
            self.assertGreater(len(cam_packets), 12)


if __name__ == "__main__":
    unittest.main()
