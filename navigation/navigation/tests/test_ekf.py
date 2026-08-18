"""
Unit Tests for 15-State Extended Kalman Filter (ekf_fusion.py).
"""

import unittest
import numpy as np

from navigation.fusion.ekf_fusion import EKFFusion
from navigation.utils.mock_generator import MockDataGenerator
from navigation.utils.math_utils import euler_to_quaternion


class TestEKFFusion(unittest.TestCase):

    def test_ekf_initialization(self):
        init_p = np.array([1.0, 2.0, 3.0])
        init_v = np.array([0.1, 0.2, 0.3])
        init_q = euler_to_quaternion(0.1, -0.2, 0.5)

        ekf = EKFFusion(init_pos=init_p, init_vel=init_v, init_quat=init_q)
        state = ekf.get_state()

        self.assertTrue(np.allclose(state["position"], init_p))
        self.assertTrue(np.allclose(state["velocity"], init_v))
        self.assertTrue(np.allclose(state["orientation_quat"], init_q))
        self.assertEqual(ekf.P.shape, (15, 15))
        # Verify covariance matrix is symmetric and positive-definite
        self.assertTrue(np.allclose(ekf.P, ekf.P.T))
        eigenvalues = np.linalg.eigvals(ekf.P)
        self.assertTrue(np.all(eigenvalues > 0))

    def test_ekf_prediction_stationary(self):
        """Stationary hover with +9.81 m/s^2 specific force should produce zero velocity & position shift."""
        ekf = EKFFusion(init_pos=np.array([0.0, 0.0, 5.0]))
        accel_stationary = np.array([0.0, 0.0, 9.81])
        gyro_stationary = np.zeros(3)

        for _ in range(100):  # 1.0 second @ 100 Hz
            state = ekf.predict(accel_stationary, gyro_stationary, dt=0.01)

        self.assertTrue(np.allclose(state["position"], [0.0, 0.0, 5.0], atol=1e-3))
        self.assertTrue(np.allclose(state["velocity"], [0.0, 0.0, 0.0], atol=1e-3))

    def test_ekf_vo_measurement_update(self):
        """Measurement update should pull position towards measurement and reduce covariance."""
        ekf = EKFFusion(init_pos=np.array([0.0, 0.0, 0.0]))
        initial_pos_var = ekf.P[0, 0]

        # Simulate noisy VO measurement at x = 1.0m
        vo_pos = np.array([1.0, 0.0, 0.0])
        vo_quat = np.array([1.0, 0.0, 0.0, 0.0])

        state = ekf.update_vo_pose(vo_pos, vo_quat, confidence=0.9)

        # Position should have moved toward 1.0
        self.assertGreater(state["position"][0], 0.0)
        # Position variance in P should have reduced
        self.assertLess(ekf.P[0, 0], initial_pos_var)

    def test_ekf_position_only_update(self):
        ekf = EKFFusion(init_pos=np.array([0.0, 0.0, 2.0]))
        ekf.update_position_only(np.array([0.0, 0.0, 5.0]), std_dev=0.05)
        state = ekf.get_state()
        self.assertGreater(state["position"][2], 3.5)

    def test_ekf_synthetic_flight_fusion(self):
        """Fused tracking across 2.0-second synthetic flight trajectory."""
        gen = MockDataGenerator(trajectory_type="figure_eight", duration=2.0, imu_hz=100, camera_hz=30)
        init_gt = gen.trajectory.get_state(0.0)

        ekf = EKFFusion(
            init_pos=init_gt["position"],
            init_vel=init_gt["velocity"],
            init_quat=init_gt["orientation_quat"]
        )

        prev_time = 0.0
        pos_errors = []

        for sensor_type, packet in gen.stream_dataset():
            ts = packet["timestamp"]
            dt = max(ts - prev_time, 0.01) if prev_time > 0 else 0.01
            prev_time = ts

            if sensor_type == "imu":
                ekf.predict(packet["accel"], packet["gyro"], dt=dt)
            elif sensor_type == "camera":
                gt = packet["ground_truth"]
                # Simulate VO pose with 2cm Gaussian noise
                noisy_pos = gt["position"] + np.random.normal(0, 0.02, 3)
                state = ekf.update_vo_pose(noisy_pos, gt["orientation_quat"], confidence=0.85)

                err = np.linalg.norm(state["position"] - gt["position"])
                pos_errors.append(err)

        mean_error = np.mean(pos_errors)
        self.assertLess(mean_error, 0.10, f"Mean error {mean_error:.4f}m too high")


if __name__ == "__main__":
    unittest.main()
