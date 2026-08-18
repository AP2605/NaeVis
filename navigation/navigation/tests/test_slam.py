"""
Unit Tests for Visual SLAM & 3D Map Management (keyframe.py, map_point.py, map_manager.py).
"""

import unittest
import numpy as np
import cv2

from navigation.slam.keyframe import KeyFrame
from navigation.slam.map_point import MapPoint
from navigation.slam.map_manager import MapManager
from navigation.utils.mock_generator import MockDataGenerator
from navigation.visual_odometry.orb_tracker import ORBTracker
from navigation.utils.math_utils import create_transform_matrix, euler_to_rotation_matrix


class TestVisualSLAM(unittest.TestCase):

    def setUp(self):
        self.K = np.array([
            [800.0,   0.0, 640.0],
            [  0.0, 800.0, 360.0],
            [  0.0,   0.0,   1.0]
        ], dtype=np.float64)

    def test_keyframe_creation_and_connections(self):
        T1 = np.eye(4)
        T2 = np.eye(4)
        T2[0, 3] = 1.0

        kf1 = KeyFrame(frame_id=1, timestamp=0.033, pose_wc=T1, keypoints=[], descriptors=np.empty((0, 32)))
        kf2 = KeyFrame(frame_id=2, timestamp=0.066, pose_wc=T2, keypoints=[], descriptors=np.empty((0, 32)))

        self.assertEqual(kf1.frame_id, 1)
        self.assertEqual(kf2.frame_id, 2)
        self.assertTrue(np.allclose(kf1.position, [0, 0, 0]))
        self.assertTrue(np.allclose(kf2.position, [1, 0, 0]))

        # Connect keyframes with 20 shared points
        kf1.add_connection(kf2, shared_count=20)
        kf2.add_connection(kf1, shared_count=20)

        covisible_kf1 = kf1.get_covisible_keyframes(min_shared=15)
        self.assertEqual(len(covisible_kf1), 1)
        self.assertEqual(covisible_kf1[0], kf2)

    def test_mappoint_reprojection_error(self):
        T_cam = np.eye(4)
        kf = KeyFrame(frame_id=1, timestamp=0.0, pose_wc=T_cam, keypoints=[], descriptors=np.empty((0, 32)))

        # 3D Landmark at (0.5, 0.2, 4.0)
        p_w = np.array([0.5, 0.2, 4.0])
        mp = MapPoint(pos_world=p_w)

        # Expected 2D pixel projection
        u_true = (800.0 * 0.5 / 4.0) + 640.0
        v_true = (800.0 * 0.2 / 4.0) + 360.0

        # Simulate observed keypoint with 0.5px noise
        kp = cv2.KeyPoint(x=u_true + 0.3, y=v_true + 0.4, size=10)
        kf.keypoints = [kp]

        mp.add_observation(kf, kp_idx=0)
        err = mp.get_reprojection_error(kf, self.K)
        self.assertAlmostEqual(err, 0.5, places=2)

    def test_map_manager_keyframe_heuristics(self):
        mm = MapManager(camera_matrix=self.K, min_translation_threshold=0.30, min_rotation_threshold=0.15)

        T_0 = np.eye(4)
        self.assertTrue(mm.is_keyframe_needed(T_0))  # First frame triggers keyframe

        kf1 = mm.insert_keyframe(1, 0.0, T_0, [], np.empty((0, 32)))

        # Small translation (0.1m) -> False
        T_small = np.eye(4)
        T_small[0, 3] = 0.10
        self.assertFalse(mm.is_keyframe_needed(T_small))

        # Large translation (0.4m) -> True
        T_large = np.eye(4)
        T_large[0, 3] = 0.40
        self.assertTrue(mm.is_keyframe_needed(T_large))

    def test_synthetic_triangulation_and_map_creation(self):
        """Triangulates 3D points between two camera views of synthetic scene."""
        gen = MockDataGenerator(trajectory_type="circular", duration=0.5, camera_hz=30)
        frames = []
        gt_poses = []

        for sensor_type, packet in gen.stream_dataset():
            if sensor_type == "camera":
                frames.append(packet["frame"])
                gt = packet["ground_truth"]
                # Camera pose T_wc
                R_wb = gt["rotation_matrix"]
                p_wb = gt["position"]
                R_bc = np.array([[0, -1, 0], [0, 0, -1], [1, 0, 0]], dtype=np.float64)
                R_wc = R_wb @ R_bc
                T_wc = create_transform_matrix(R_wc, p_wb)
                gt_poses.append(T_wc)

                if len(frames) >= 2:
                    break

        tracker = ORBTracker(n_features=2000, fast_threshold=10, ratio_threshold=0.80)
        kp1, des1 = tracker.detect_and_compute(frames[0])
        kp2, des2 = tracker.detect_and_compute(frames[1])

        pts1, pts2, matches = tracker.match(des1, des2, kp1, kp2)
        self.assertGreater(len(matches), 15)

        mm = MapManager(camera_matrix=self.K, max_reprojection_error=4.0)

        kf1 = mm.insert_keyframe(1, 0.0, gt_poses[0], kp1, des1)
        kf2 = mm.insert_keyframe(2, 0.033, gt_poses[1], kp2, des2)

        new_points = mm.triangulate_points(kf1, kf2, matches, pts1, pts2)
        print(f"Triangulated {len(new_points)} 3D MapPoints using ground truth baseline.")

        self.assertGreaterEqual(len(new_points), 3)
        self.assertGreaterEqual(len(mm.map_points), 3)

        point_cloud = mm.get_sparse_point_cloud()
        self.assertEqual(point_cloud.shape[1], 3)


if __name__ == "__main__":
    unittest.main()
