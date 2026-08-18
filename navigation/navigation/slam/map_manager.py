"""
Visual SLAM Map Manager Module (P3 Module).
===========================================
Orchestrates the persistent 3D spatial map for GPS-denied navigation:
  - Keyframe decision heuristics (distance, rotation, and tracking drop thresholds).
  - 3D Landmark Triangulation via Direct Linear Transform (DLT).
  - Reprojection error checking & outlier landmark pruning.
  - Covisibility graph maintenance for local tracking and loop closure.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import cv2

from navigation.slam.keyframe import KeyFrame
from navigation.slam.map_point import MapPoint
from navigation.utils.math_utils import invert_transform_matrix, quaternion_to_euler, rotation_matrix_to_quaternion


class MapManager:
    """
    Manages the 3D point cloud map, KeyFrame graph, and multi-view triangulation.
    """

    def __init__(
        self,
        camera_matrix: Optional[np.ndarray] = None,
        min_translation_threshold: float = 0.25, # meters
        min_rotation_threshold: float = 0.14,    # ~8 degrees
        max_reprojection_error: float = 3.0       # pixels
    ):
        if camera_matrix is not None:
            self.K = np.array(camera_matrix, dtype=np.float64)
        else:
            self.K = np.array([
                [800.0,   0.0, 640.0],
                [  0.0, 800.0, 360.0],
                [  0.0,   0.0,   1.0]
            ], dtype=np.float64)

        self.min_translation_threshold = min_translation_threshold
        self.min_rotation_threshold = min_rotation_threshold
        self.max_reprojection_error = max_reprojection_error

        self.keyframes: List[KeyFrame] = []
        self.map_points: List[MapPoint] = []
        self.last_keyframe: Optional[KeyFrame] = None

    def is_keyframe_needed(
        self,
        current_pose_wc: np.ndarray,
        num_inliers: int = 20,
        total_matches: int = 30
    ) -> bool:
        """
        Evaluates whether the current frame meets the heuristics to spawn a new KeyFrame.
        """
        if self.last_keyframe is None:
            return True  # First frame is always a keyframe

        # 1. Translation delta
        last_pos = self.last_keyframe.position
        curr_pos = current_pose_wc[:3, 3]
        dist = float(np.linalg.norm(curr_pos - last_pos))

        if dist >= self.min_translation_threshold:
            return True

        # 2. Rotation delta
        R_last = self.last_keyframe.rotation
        R_curr = current_pose_wc[:3, :3]
        R_rel = R_last.T @ R_curr
        # Trace of rotation matrix: tr(R) = 1 + 2*cos(theta)
        cos_theta = np.clip((np.trace(R_rel) - 1.0) / 2.0, -1.0, 1.0)
        angle_rad = float(np.arccos(cos_theta))

        if angle_rad >= self.min_rotation_threshold:
            return True

        # 3. Tracking feature drop below 60%
        if total_matches > 0 and (num_inliers / total_matches) < 0.60:
            return True

        return False

    def insert_keyframe(
        self,
        frame_id: int,
        timestamp: float,
        pose_wc: np.ndarray,
        keypoints: List[cv2.KeyPoint],
        descriptors: np.ndarray
    ) -> KeyFrame:
        """Creates and stores a new KeyFrame in the map."""
        kf = KeyFrame(
            frame_id=frame_id,
            timestamp=timestamp,
            pose_wc=pose_wc,
            keypoints=keypoints,
            descriptors=descriptors
        )
        self.keyframes.append(kf)
        self.last_keyframe = kf
        return kf

    def triangulate_points(
        self,
        kf1: KeyFrame,
        kf2: KeyFrame,
        good_matches: List[cv2.DMatch],
        pts1: np.ndarray,
        pts2: np.ndarray
    ) -> List[MapPoint]:
        """
        Triangulates 3D MapPoints from 2D point correspondences across two KeyFrames.
        """
        if len(good_matches) == 0 or len(pts1) == 0 or len(pts2) == 0:
            return []

        # 1. 3x4 Projection Matrices: P = K * [R_cw | t_cw]
        P1 = self.K @ kf1.pose_cw[:3, :]
        P2 = self.K @ kf2.pose_cw[:3, :]

        # 2. Triangulate points using OpenCV DLT solver
        pts1_t = pts1.T  # 2xN
        pts2_t = pts2.T  # 2xN
        pts4d = cv2.triangulatePoints(P1, P2, pts1_t, pts2_t)  # 4xN

        new_map_points = []

        R_cw1, t_cw1 = kf1.pose_cw[:3, :3], kf1.pose_cw[:3, 3]
        R_cw2, t_cw2 = kf2.pose_cw[:3, :3], kf2.pose_cw[:3, 3]

        for i, match in enumerate(good_matches):
            w = pts4d[3, i]
            if abs(w) < 1e-6:
                continue

            # Convert to Euclidean 3D world coordinate [X, Y, Z]
            p_w = pts4d[:3, i] / w

            # 3. Cheirality Check: Point must be in front of both cameras (Z_c > 0.3)
            p_c1 = R_cw1 @ p_w + t_cw1
            p_c2 = R_cw2 @ p_w + t_cw2

            if p_c1[2] < 0.3 or p_c2[2] < 0.3:
                continue

            # 4. Reprojection Error Check on both cameras
            u1_proj = (self.K[0, 0] * p_c1[0] / p_c1[2]) + self.K[0, 2]
            v1_proj = (self.K[1, 1] * p_c1[1] / p_c1[2]) + self.K[1, 2]
            err1 = np.sqrt((pts1[i, 0] - u1_proj) ** 2 + (pts1[i, 1] - v1_proj) ** 2)

            u2_proj = (self.K[0, 0] * p_c2[0] / p_c2[2]) + self.K[0, 2]
            v2_proj = (self.K[1, 1] * p_c2[1] / p_c2[2]) + self.K[1, 2]
            err2 = np.sqrt((pts2[i, 0] - u2_proj) ** 2 + (pts2[i, 1] - v2_proj) ** 2)

            if err1 > self.max_reprojection_error or err2 > self.max_reprojection_error:
                continue

            # 5. Extract representative descriptor
            des = kf2.descriptors[match.trainIdx] if kf2.descriptors is not None else None

            mp = MapPoint(pos_world=p_w, descriptor=des, first_keyframe=kf1, first_kp_idx=match.queryIdx)
            mp.add_observation(kf2, match.trainIdx)

            self.map_points.append(mp)
            new_map_points.append(mp)

        # Update covisibility graph
        self.update_covisibility_graph()
        return new_map_points

    def update_covisibility_graph(self):
        """Builds weighted graph edges between keyframes that share common 3D landmarks."""
        for i, kf1 in enumerate(self.keyframes):
            for kf2 in self.keyframes[i + 1:]:
                # Find count of shared map points
                shared_pts = 0
                for mp1 in kf1.map_points.values():
                    if mp1 in kf2.map_points.values():
                        shared_pts += 1

                if shared_pts >= 5:
                    kf1.add_connection(kf2, shared_pts)
                    kf2.add_connection(kf1, shared_pts)

    def prune_map(self):
        """Removes bad or outlier MapPoints."""
        active_points = []
        for mp in self.map_points:
            if not mp.is_bad and mp.num_observations >= 2:
                active_points.append(mp)
            else:
                mp.is_bad = True
        self.map_points = active_points

    def get_sparse_point_cloud(self) -> np.ndarray:
        """Returns (N, 3) array of active 3D landmark coordinates in world frame."""
        if not self.map_points:
            return np.empty((0, 3), dtype=np.float64)
        return np.array([mp.pos_world for mp in self.map_points if not mp.is_bad], dtype=np.float64)

    def get_statistics(self) -> Dict[str, Any]:
        """Returns SLAM map health metrics."""
        return {
            "num_keyframes": len(self.keyframes),
            "num_map_points": len(self.map_points),
            "num_active_points": len([mp for mp in self.map_points if not mp.is_bad]),
            "last_keyframe_id": self.last_keyframe.id if self.last_keyframe else None
        }


if __name__ == "__main__":
    print("=== Testing MapManager ===")
    mm = MapManager()

    # Test KeyFrame Decision
    T_init = np.eye(4)
    self_need = mm.is_keyframe_needed(T_init)
    print(f"First frame needs keyframe: {self_need}")
    assert self_need is True

    kf1 = mm.insert_keyframe(frame_id=1, timestamp=0.0, pose_wc=T_init, keypoints=[], descriptors=np.empty((0, 32)))

    # Move 0.1m (should not trigger)
    T_small = np.eye(4)
    T_small[0, 3] = 0.10
    self_need_small = mm.is_keyframe_needed(T_small)
    assert self_need_small is False

    # Move 0.5m (should trigger)
    T_large = np.eye(4)
    T_large[0, 3] = 0.50
    self_need_large = mm.is_keyframe_needed(T_large)
    assert self_need_large is True

    stats = mm.get_statistics()
    print(f"Map Stats: {stats}")
    print("MapManager verification PASSED!")
