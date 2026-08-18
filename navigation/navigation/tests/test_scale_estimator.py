"""
Unit Tests for Metric Scale Estimator (scale_estimator.py).
"""

import unittest
import numpy as np

from navigation.visual_odometry.scale_estimator import ScaleEstimator


class TestScaleEstimator(unittest.TestCase):

    def test_initial_and_default_scale(self):
        estimator = ScaleEstimator(default_scale=0.08)
        self.assertAlmostEqual(estimator.get_current_scale(), 0.08)

    def test_motion_gating_at_hover(self):
        """At zero acceleration (hover), scale should not blow up or jump."""
        estimator = ScaleEstimator(default_scale=0.067, min_accel_threshold=0.10)

        a_zero = np.zeros(3)
        v_zero = np.zeros(3)
        vo_unit = np.array([1.0, 0.0, 0.0])

        for _ in range(20):
            estimator.add_imu_sample(a_zero, v_zero, dt=0.01)
            scale = estimator.estimate_scale(vo_unit, dt=0.033)

        self.assertAlmostEqual(scale, 0.067, places=3)

    def test_scale_convergence_under_acceleration(self):
        """Under sustained forward motion and acceleration, scale converges toward physical displacement."""
        estimator = ScaleEstimator(default_scale=0.02, alpha=0.3, min_accel_threshold=0.05)

        # Simulating 3.0 m/s flight (approx 0.10 m per 30 FPS frame)
        v_flight = np.array([3.0, 0.0, 0.0])
        a_flight = np.array([0.5, 0.0, 0.0])
        vo_unit = np.array([1.0, 0.0, 0.0])

        for _ in range(40):
            for _ in range(3):
                estimator.add_imu_sample(a_flight, v_flight, dt=0.01)
            scale = estimator.estimate_scale(vo_unit, dt=0.033)

        # Scale should have increased from 0.02 toward ~0.10-0.15 m/frame
        self.assertGreater(scale, 0.05)
        self.assertLessEqual(scale, 0.25)

    def test_altitude_fusion_constraint(self):
        """Direct vertical movement with altitude sensor update."""
        estimator = ScaleEstimator(default_scale=0.05, alpha=0.5)

        vo_unit_z = np.array([0.0, 0.0, 1.0])
        scale = estimator.estimate_scale(vo_unit_z, dt=0.033, altitude_change=0.20)

        self.assertGreater(scale, 0.10)

    def test_reset(self):
        estimator = ScaleEstimator(default_scale=0.05)
        estimator.estimate_scale(np.array([1.0, 0.0, 0.0]), dt=0.033, altitude_change=0.50)
        estimator.reset(initial_scale=0.07)
        self.assertAlmostEqual(estimator.get_current_scale(), 0.07)
        self.assertEqual(len(estimator.imu_buffer), 0)
        self.assertEqual(len(estimator.vo_buffer), 0)


if __name__ == "__main__":
    unittest.main()
