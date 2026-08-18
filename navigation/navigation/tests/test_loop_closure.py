"""
Unit Tests for Loop Closure & Place Recognition (loop_closure.py).
"""

import unittest
import numpy as np
import cv2

from navigation.slam.keyframe import KeyFrame
from navigation.slam.map_point import MapPoint
from navigation.slam.map_manager import MapManager
from navigation.slam.loop_closure import LoopCloser
from navigation.utils.math_utils import create_transform_matrix


class TestLoopClosure(unittest.TestCase):

    def setUp(self):
        self.K = np.array([
            [800.0,   0.0, 640.0],
            [  0.0, 800.0, 360.0],
            [  0.0,   0.0,   1.0]
        ], dtype=np.float64)

    def test_loop_closer_initialization(self):
        lc = LoopCloser(camera_matrix=self.K, min_inliers=10, temporal_window=5)
        self.assertEqual(lc.min_inliers, 10)
        self.assertEqual(lc.temporal_window, 5)
        self.assertEqual(lc.loop_count, 0)

    def test_temporal_window_exclusion(self):
        """Keyframes within the recent temporal window must not trigger loop closures."""
        lc = LoopCloser(temporal_window=8)
        mm = MapManager(camera_matrix=self.K)

        # Create 5 keyframes (fewer than temporal window)
        for i in range(5):
            T = np.eye(4)
            T[0, 3] = float(i)
            kf = mm.insert_keyframe(i, float(i) * 0.033, T, [], np.empty((0, 32)))

        res = lc.detect_and_verify_loop(mm.keyframes[-1], mm)
        self.assertIsNone(res, "Expected None when historical keyframes < temporal window")

    def test_pose_graph_drift_correction(self):
        """Verifies that Pose Graph Optimization smoothly corrects accumulated drift across a loop."""
        lc = LoopCloser(temporal_window=5)
        mm = MapManager(camera_matrix=self.K)

        # Simulate 12 keyframes in a circular flight from (0,0) back to (0,0)
        num_kf = 12
        radius = 5.0

        for i in range(num_kf):
            theta = (2.0 * np.pi / (num_kf - 1)) * i
            pos_true = np.array([radius * np.cos(theta), radius * np.sin(theta), 5.0])

            # Inject artificial linear drift that grows to 1.2 meters by the last frame
            drift_err = np.array([0.1 * i, 0.0, 0.0])
            pos_drifted = pos_true + drift_err

            T = np.eye(4)
            T[:3, 3] = pos_drifted
            mm.insert_keyframe(i, float(i) * 0.1, T, [], np.empty((0, 32)))

        start_kf = mm.keyframes[0]   # True position: (5.0, 0.0, 5.0)
        end_kf = mm.keyframes[-1]    # Drifted position: (5.0 + 1.1, 0.0, 5.0)

        initial_drift = np.linalg.norm(end_kf.position - start_kf.position)
        self.assertGreater(initial_drift, 1.0, "Expected significant initial drift")

        # Apply loop closure: end_kf should snap back to start_kf pose
        corrected_pose = np.eye(4)
        corrected_pose[:3, 3] = start_kf.position

        report = lc.optimize_pose_graph(end_kf, start_kf, corrected_pose, mm)

        # Verify loop closure results
        self.assertEqual(report["loop_id"], 1)
        self.assertGreaterEqual(report["keyframes_corrected"], 10)

        # Verify final keyframe is now back at start position (zero drift!)
        final_error = np.linalg.norm(end_kf.position - start_kf.position)
        self.assertAlmostEqual(final_error, 0.0, places=5)
        print(f"Loop Closure successfully eliminated {initial_drift:.3f}m drift to {final_error:.5f}m!")


if __name__ == "__main__":
    unittest.main()
