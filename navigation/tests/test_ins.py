"""
Unit Tests for INS Dead Reckoning Module (imu_integrator.py).
"""

import unittest
import numpy as np

from navigation.ins.imu_integrator import IMUIntegrator
from navigation.utils.mock_generator import MockDataGenerator


class TestINS(unittest.TestCase):

    def test_static_gravity_cancellation(self):
        """Stationary drone measuring +1g reaction force should produce zero linear acceleration."""
        ins = IMUIntegrator(init_pos=np.array([0.0, 0.0, 5.0]))
        stationary_accel = np.array([0.0, 0.0, 9.81])
        stationary_gyro = np.array([0.0, 0.0, 0.0])

        for _ in range(100):  # 1.0 second @ 100 Hz
            state = ins.update(stationary_accel, stationary_gyro, dt=0.01)

        self.assertTrue(np.allclose(state["position"], [0.0, 0.0, 5.0], atol=1e-3))
        self.assertTrue(np.allclose(state["velocity"], [0.0, 0.0, 0.0], atol=1e-3))
        self.assertTrue(np.allclose(state["linear_accel_world"], [0.0, 0.0, 0.0], atol=1e-3))

    def test_pure_linear_acceleration(self):
        """Constant 2 m/s^2 acceleration along X-axis for 1 second should give v=2, p=1."""
        ins = IMUIntegrator(init_pos=np.zeros(3), init_vel=np.zeros(3))
        accel_body = np.array([2.0, 0.0, 9.81])  # 2 m/s^2 forward + gravity
        gyro_body = np.zeros(3)

        dt = 0.01
        for _ in range(100):  # 1.0 second total
            state = ins.update(accel_body, gyro_body, dt=dt)

        self.assertAlmostEqual(state["velocity"][0], 2.0, places=2)
        self.assertAlmostEqual(state["position"][0], 1.0, places=2)

    def test_dynamic_bias_and_reset(self):
        ins = IMUIntegrator()
        ins.set_biases(accel_bias=np.array([0.05, -0.02, 0.01]), gyro_bias=np.array([0.001, 0.0, -0.002]))

        self.assertTrue(np.allclose(ins.accel_bias, [0.05, -0.02, 0.01]))
        self.assertTrue(np.allclose(ins.gyro_bias, [0.001, 0.0, -0.002]))

        ins.reset_state(pos=np.array([10.0, 20.0, 30.0]), vel=np.array([1.0, 2.0, 3.0]))
        state = ins.get_state()
        self.assertTrue(np.allclose(state["position"], [10.0, 20.0, 30.0]))
        self.assertTrue(np.allclose(state["velocity"], [1.0, 2.0, 3.0]))

    def test_synthetic_flight_dead_reckoning(self):
        """Integration across 3-second synthetic flight stream."""
        gen = MockDataGenerator(trajectory_type="circular", duration=3.0, imu_hz=100, add_sensor_noise=False)
        init_gt = gen.trajectory.get_state(0.0)

        ins = IMUIntegrator(
            init_pos=init_gt["position"],
            init_vel=init_gt["velocity"],
            init_quat=init_gt["orientation_quat"]
        )

        prev_time = 0.0
        for sensor_type, packet in gen.stream_dataset():
            if sensor_type == "imu":
                dt = max(packet["timestamp"] - prev_time, 0.01)
                prev_time = packet["timestamp"]
                state = ins.update(packet["accel"], packet["gyro"], dt=dt)

        final_gt = gen.trajectory.get_state(3.0)
        drift = np.linalg.norm(state["position"] - final_gt["position"])
        # With noise-free IMU, 3s integration drift should be under 1.5 meters
        self.assertLess(drift, 1.5, f"Drift {drift:.3f}m was higher than expected")


if __name__ == "__main__":
    unittest.main()
