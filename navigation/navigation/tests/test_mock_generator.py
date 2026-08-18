"""
Unit Tests for Mock Data Generator (mock_generator.py).
"""

import unittest
import os
import tempfile
import numpy as np

from navigation.utils.mock_generator import (
    SyntheticTrajectory,
    SyntheticIMU,
    SyntheticCameraEnvironment,
    MockDataGenerator
)


class TestMockGenerator(unittest.TestCase):

    def test_trajectory_profiles(self):
        profiles = ["figure_eight", "circular", "straight_line", "hover"]
        for profile in profiles:
            traj = SyntheticTrajectory(trajectory_type=profile, duration=5.0)
            state_0 = traj.get_state(0.0)
            state_mid = traj.get_state(2.5)

            self.assertIn("position", state_0)
            self.assertIn("velocity", state_0)
            self.assertIn("acceleration", state_0)
            self.assertIn("orientation_quat", state_0)
            self.assertIn("rotation_matrix", state_0)

            # Quaternions must be unit length
            self.assertAlmostEqual(np.linalg.norm(state_0["orientation_quat"]), 1.0, places=6)
            self.assertAlmostEqual(np.linalg.norm(state_mid["orientation_quat"]), 1.0, places=6)

    def test_imu_gravity_measurement(self):
        imu = SyntheticIMU(accel_noise_std=0.0, gyro_noise_std=0.0, accel_bias=np.zeros(3), gyro_bias=np.zeros(3))
        # Stationary state (accel=0, rotation=identity)
        stationary_gt = {
            "timestamp": 0.0,
            "acceleration": np.array([0.0, 0.0, 0.0]),
            "rotation_matrix": np.eye(3),
            "angular_velocity": np.array([0.0, 0.0, 0.0])
        }
        meas = imu.measure(stationary_gt)
        # Stationary accelerometer measures +1g reaction force [0, 0, +9.81]
        self.assertTrue(np.allclose(meas["accel"], [0.0, 0.0, 9.81], atol=1e-3))
        self.assertTrue(np.allclose(meas["gyro"], [0.0, 0.0, 0.0], atol=1e-3))

    def test_camera_1280x720_rendering(self):
        cam = SyntheticCameraEnvironment(width=1280, height=720)
        gt_state = {
            "position": np.array([0.0, 0.0, 5.0]),
            "rotation_matrix": np.eye(3)
        }
        frame, visible_lms = cam.render_frame(gt_state)
        self.assertEqual(frame.shape, (720, 1280, 3))
        self.assertGreater(len(visible_lms), 20, "Expected at least 20 visible landmarks in view")

    def test_stream_dataset_synchronization(self):
        gen = MockDataGenerator(trajectory_type="circular", duration=1.0, imu_hz=100, camera_hz=30)
        timestamps = []
        imu_count = 0
        cam_count = 0

        for sensor_type, packet in gen.stream_dataset():
            ts = packet["timestamp"]
            timestamps.append(ts)
            if sensor_type == "imu":
                imu_count += 1
            elif sensor_type == "camera":
                cam_count += 1

        # Check timestamps are monotonically increasing
        for i in range(len(timestamps) - 1):
            self.assertLessEqual(timestamps[i], timestamps[i + 1] + 1e-9)

        self.assertGreaterEqual(imu_count, 99)
        self.assertGreaterEqual(cam_count, 29)

    def test_export_dataset_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            gen = MockDataGenerator(trajectory_type="hover", duration=0.5, imu_hz=100, camera_hz=30)
            gen.export_dataset_to_disk(tmp_dir)

            # Check exported files exist
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "imu.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "telemetry.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "imu.csv")))
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "ground_truth.csv")))
            self.assertTrue(os.path.isdir(os.path.join(tmp_dir, "images")))

            images = os.listdir(os.path.join(tmp_dir, "images"))
            self.assertGreater(len(images), 10)
            self.assertIn("frame_000001.png", images)


if __name__ == "__main__":
    unittest.main()
