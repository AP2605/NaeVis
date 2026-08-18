"""
Stress & Robustness Test Suite for GPS-Denied Navigation (P3 Module).
=====================================================================
Validates system resilience under challenging flight conditions:
  - Visual dropout / camera occlusion (fog, lens flare, darkness).
  - High IMU sensor noise and vibration stress.
  - Aggressive 3D high-yaw maneuvers (Gimbal lock immunity).
"""

import unittest
import numpy as np

from navigation.engine import NavigationEngine
from navigation.fusion.ekf_fusion import EKFFusion
from navigation.utils.mock_generator import MockDataGenerator
from navigation.utils.math_utils import quaternion_to_euler, quaternion_normalize


class TestRobustness(unittest.TestCase):

    def test_camera_occlusion_and_imu_fallback(self):
        """
        Simulates flying into heavy fog / complete visual occlusion:
        The engine must smoothly fall back to high-rate IMU dead reckoning,
        then seamlessly re-engage visual odometry when visibility clears.
        """
        engine = NavigationEngine()
        gen = MockDataGenerator(trajectory_type="straight_line", duration=1.0, camera_hz=30)

        packet_id = 0
        states_recorded = []

        for sensor_type, packet in gen.stream_dataset():
            if sensor_type == "camera":
                packet_id += 1
                gt = packet["ground_truth"]

                # Frames 10-20 are completely occluded (black/fog frames)
                if 10 <= packet_id <= 20:
                    frame_input = np.zeros((720, 1280, 3), dtype=np.uint8) # black image
                else:
                    frame_input = packet["frame"]

                sensor_packet = {
                    "frame_id": packet_id,
                    "timestamp": packet["timestamp"],
                    "camera": {"frame": frame_input, "width": 1280, "height": 720},
                    "imu": {
                        "acceleration": list(gt["acceleration"] + np.array([0, 0, 9.81])),
                        "gyroscope": list(gt["angular_velocity"])
                    }
                }

                out = engine.process_packet(sensor_packet)
                states_recorded.append(out["tracking_state"])

        # Check that engine did not crash and reported appropriate state
        self.assertEqual(len(states_recorded), 31)
        # During occlusion (frames 10-20), tracking state drops or relies on IMU
        self.assertIn(states_recorded[15], ["INSUFFICIENT_FEATURES", "TRACKING_POOR", "PREDICTING_IMU_ONLY", "INITIALIZING"])
        # After frame 20, visual tracking recovers
        self.assertIn(states_recorded[-1], ["TRACKING_GOOD", "TRACKING_POOR"])

    def test_extreme_imu_noise_rejection(self):
        """15-State EKF should filter out high-frequency sensor noise."""
        ekf = EKFFusion(init_pos=np.array([0.0, 0.0, 5.0]))

        # Feed 1.0s of noisy stationary IMU data (10x noise)
        for _ in range(100):
            noisy_acc = np.array([0.0, 0.0, 9.81]) + np.random.normal(0, 0.5, 3)
            noisy_gyr = np.random.normal(0, 0.05, 3)
            ekf.predict(noisy_acc, noisy_gyr, dt=0.01)

        state = ekf.get_state()
        # Velocity and position should remain reasonably bounded near origin
        self.assertLess(np.linalg.norm(state["velocity"]), 1.5)
        self.assertLess(abs(state["position"][2] - 5.0), 1.0)

    def test_gimbal_lock_immunity_in_360_spin(self):
        """Aggressive yaw spin of 720 degrees must not cause gimbal lock or numerical instability."""
        ekf = EKFFusion()

        # Spin around Z-axis at 6.28 rad/s (1 revolution per second) for 2 seconds
        spin_gyro = np.array([0.0, 0.0, 6.283185])
        accel_stat = np.array([0.0, 0.0, 9.81])

        for _ in range(200): # 2.0s @ 100 Hz
            ekf.predict(accel_stat, spin_gyro, dt=0.01)

        state = ekf.get_state()
        q = state["orientation_quat"]
        # Quaternion must remain exactly unit length
        self.assertAlmostEqual(np.linalg.norm(q), 1.0, places=5)
        # Position should stay virtually stationary
        self.assertLess(np.linalg.norm(state["position"]), 0.1)


if __name__ == "__main__":
    unittest.main()
