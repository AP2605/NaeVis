"""
Unit Tests for Visual Odometry Modules (orb_tracker.py & vo_estimator.py).
"""

import unittest
import numpy as np

from navigation.visual_odometry.orb_tracker import ORBTracker
from navigation.visual_odometry.vo_estimator import VisualOdometryEstimator
from navigation.utils.mock_generator import MockDataGenerator


class TestVisualOdometry(unittest.TestCase):

    def setUp(self):
        self.gen = MockDataGenerator(trajectory_type="circular", duration=1.0, camera_hz=30)
        self.frames = []
        for sensor_type, packet in self.gen.stream_dataset():
            if sensor_type == "camera":
                self.frames.append(packet["frame"])
                if len(self.frames) >= 10:
                    break

    def test_orb_tracker_extraction_and_matching(self):
        tracker = ORBTracker(n_features=2000, fast_threshold=10, ratio_threshold=0.80)
        self.assertGreaterEqual(len(self.frames), 2)

        kp1, des1 = tracker.detect_and_compute(self.frames[0])
        kp2, des2 = tracker.detect_and_compute(self.frames[1])

        self.assertGreater(len(kp1), 100)
        self.assertGreater(len(kp2), 100)
        self.assertEqual(des1.shape[1], 32)  # 256-bit binary descriptors = 32 bytes

        pts1, pts2, matches = tracker.match(des1, des2, kp1, kp2)
        self.assertGreaterEqual(len(matches), 15, "Expected at least 15 valid feature matches")
        self.assertEqual(len(pts1), len(matches))
        self.assertEqual(len(pts2), len(matches))

    def test_vo_initialization_and_tracking(self):
        vo = VisualOdometryEstimator(min_inliers=6)

        # Frame 1: Initializing
        res1 = vo.process_frame(self.frames[0])
        self.assertEqual(res1["tracking_state"], "INITIALIZING")
        self.assertEqual(res1["num_inliers"], 0)

        # Frame 2: Tracking Good
        res2 = vo.process_frame(self.frames[1], scale=0.1)
        self.assertIn(res2["tracking_state"], ["TRACKING_GOOD", "TRACKING_POOR"])
        self.assertIn("relative_R", res2)
        self.assertIn("relative_t", res2)
        self.assertIn("confidence", res2)

    def test_vo_multi_frame_trajectory(self):
        vo = VisualOdometryEstimator(min_inliers=6)
        inlier_counts = []

        for frame in self.frames:
            res = vo.process_frame(frame, scale=0.05)
            if res["frame_idx"] > 1:
                inlier_counts.append(res["num_inliers"])

        avg_inliers = np.mean(inlier_counts) if inlier_counts else 0
        self.assertGreaterEqual(avg_inliers, 5, "Expected average inliers >= 5")

    def test_vo_reset(self):
        vo = VisualOdometryEstimator()
        vo.process_frame(self.frames[0])
        vo.process_frame(self.frames[1])

        # Reset pose to custom 4x4 matrix
        T_custom = np.eye(4)
        T_custom[:3, 3] = [10.0, 20.0, 30.0]
        vo.reset_pose(T_custom)

        self.assertTrue(np.allclose(vo.current_pose_wc[:3, 3], [10.0, 20.0, 30.0]))


if __name__ == "__main__":
    unittest.main()
