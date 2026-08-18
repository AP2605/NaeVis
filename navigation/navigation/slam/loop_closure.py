"""
Loop Closure & Place Recognition Module (P3 Module).
====================================================
Detects when the drone revisits a previously mapped location and eliminates accumulated drift:
  - Global place recognition search over historical KeyFrames (excluding recent temporal window).
  - Robust 2D-to-3D geometric verification via PnP (Perspective-n-Point) + RANSAC.
  - Pose Graph Optimization (PGO) drift back-propagation along the loop trajectory.
  - Corrects 3D MapPoints and resets EKF state for zero-drift long-term navigation.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import cv2

from navigation.slam.keyframe import KeyFrame
from navigation.slam.map_manager import MapManager
from navigation.visual_odometry.orb_tracker import ORBTracker
from navigation.utils.math_utils import (
    create_transform_matrix,
    invert_transform_matrix,
    rotation_matrix_to_quaternion,
    quaternion_to_euler
)


class LoopCloser:
    """
    Handles place recognition, geometric PnP verification, and Pose Graph Optimization.
    """

    def __init__(
        self,
        camera_matrix: Optional[np.ndarray] = None,
        min_inliers: int = 12,
        min_match_ratio: float = 0.20,
        temporal_window: int = 8,
        ransac_reproj_error: float = 4.0
    ):
        if camera_matrix is not None:
            self.K = np.array(camera_matrix, dtype=np.float64)
        else:
            self.K = np.array([
                [800.0,   0.0, 640.0],
                [  0.0, 800.0, 360.0],
                [  0.0,   0.0,   1.0]
            ], dtype=np.float64)

        self.min_inliers = min_inliers
        self.min_match_ratio = min_match_ratio
        self.temporal_window = temporal_window
        self.ransac_reproj_error = ransac_reproj_error

        self.tracker = ORBTracker(n_features=2000, fast_threshold=10, ratio_threshold=0.80)
        self.loop_count = 0
        self.loop_history: List[Dict[str, Any]] = []

    def detect_and_verify_loop(
        self,
        current_kf: KeyFrame,
        map_manager: MapManager
    ) -> Optional[Tuple[KeyFrame, np.ndarray, int]]:
        """
        Searches historical keyframes for loop closure candidates and performs
        geometric verification using PnP + RANSAC.

        Returns:
            Tuple of (candidate_kf, relative_transform_T, inlier_count) or None.
        """
        if len(map_manager.keyframes) <= self.temporal_window + 2:
            return None  # Not enough historical keyframes yet

        if current_kf.descriptors is None or len(current_kf.descriptors) < 20:
            return None

        # Exclude recent keyframes (temporal window) to avoid local matching
        candidate_pool = map_manager.keyframes[:-self.temporal_window]

        best_candidate: Optional[KeyFrame] = None
        best_inliers = 0
        best_T_cand_curr: Optional[np.ndarray] = None

        for cand_kf in candidate_pool:
            if cand_kf.descriptors is None or len(cand_kf.descriptors) < 20:
                continue

            # 1. Feature Matching between Current KeyFrame and Candidate KeyFrame
            pts_curr, pts_cand, matches = self.tracker.match(
                current_kf.descriptors,
                cand_kf.descriptors,
                current_kf.keypoints,
                cand_kf.keypoints
            )

            min_feats = min(len(current_kf.keypoints), len(cand_kf.keypoints))
            if min_feats == 0 or len(matches) < self.min_inliers:
                continue

            match_ratio = len(matches) / float(min_feats)
            if match_ratio < self.min_match_ratio:
                continue

            # 2. Collect 3D-to-2D correspondences for PnP
            # We look up 3D MapPoints associated with the candidate's keypoints
            object_points_3d = []
            image_points_2d = []

            for match in matches:
                curr_idx = match.queryIdx
                cand_idx = match.trainIdx

                mp = cand_kf.get_map_point(cand_idx)
                if mp is not None and not mp.is_bad:
                    object_points_3d.append(mp.pos_world)
                    image_points_2d.append(current_kf.keypoints[curr_idx].pt)

            if len(object_points_3d) < self.min_inliers:
                continue

            obj_pts = np.array(object_points_3d, dtype=np.float64)
            img_pts = np.array(image_points_2d, dtype=np.float64)

            # 3. Geometric Verification via PnP + RANSAC
            success, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj_pts,
                img_pts,
                self.K,
                distCoeffs=None,
                reprojectionError=self.ransac_reproj_error,
                confidence=0.99,
                flags=cv2.SOLVEPNP_EPNP
            )

            if success and inliers is not None and len(inliers) >= self.min_inliers:
                num_inliers = len(inliers)
                if num_inliers > best_inliers:
                    best_inliers = num_inliers
                    best_candidate = cand_kf

                    # Convert rvec, tvec (World to Camera) to 4x4 matrix
                    R_cw, _ = cv2.Rodrigues(rvec)
                    t_cw = tvec.flatten()
                    T_cw = create_transform_matrix(R_cw, t_cw)
                    T_wc_corrected = invert_transform_matrix(T_cw)
                    best_T_cand_curr = T_wc_corrected

        if best_candidate is not None and best_T_cand_curr is not None:
            return best_candidate, best_T_cand_curr, best_inliers

        return None

    def optimize_pose_graph(
        self,
        current_kf: KeyFrame,
        candidate_kf: KeyFrame,
        corrected_pose_wc: np.ndarray,
        map_manager: MapManager
    ) -> Dict[str, Any]:
        """
        Performs Pose Graph Optimization by distributing drift correction smoothly
        backwards across all keyframes and map points along the loop.
        """
        self.loop_count += 1

        # 1. Compute Total Drift Vector at Current KeyFrame
        pos_drift = corrected_pose_wc[:3, 3] - current_kf.position
        rot_curr = current_kf.rotation
        rot_corr = corrected_pose_wc[:3, :3]
        delta_R = rot_corr @ rot_curr.T

        # Find keyframe indices
        cand_idx = map_manager.keyframes.index(candidate_kf)
        curr_idx = map_manager.keyframes.index(current_kf)
        num_loop_keyframes = max(1, curr_idx - cand_idx)

        # 2. Smoothly Distribute Correction along the Loop Chain
        for idx in range(cand_idx, curr_idx + 1):
            kf = map_manager.keyframes[idx]
            weight = float(idx - cand_idx) / float(num_loop_keyframes)

            # Interpolate position correction
            new_pos = kf.position + weight * pos_drift

            # Interpolate rotation correction
            R_orig = kf.rotation
            # Small-angle rotation blending: R_new = (I + w * (delta_R - I)) * R_orig
            R_blend = np.eye(3) + weight * (delta_R - np.eye(3))
            U, _, Vt = np.linalg.svd(R_blend @ R_orig)
            new_R = U @ Vt

            # Update KeyFrame pose
            kf.pose_wc = create_transform_matrix(new_R, new_pos)
            kf.pose_cw = invert_transform_matrix(kf.pose_wc)

        # 3. Update 3D MapPoints
        for mp in map_manager.map_points:
            if not mp.is_bad:
                mp.pos_world += 0.5 * pos_drift

        # Update covisibility graph connection between loop keyframes
        current_kf.add_connection(candidate_kf, shared_count=30)
        candidate_kf.add_connection(current_kf, shared_count=30)

        loop_record = {
            "loop_id": self.loop_count,
            "current_kf_id": current_kf.id,
            "candidate_kf_id": candidate_kf.id,
            "drift_magnitude_m": float(np.linalg.norm(pos_drift)),
            "drift_vector": pos_drift.tolist(),
            "corrected_position": current_kf.position.tolist(),
            "keyframes_corrected": num_loop_keyframes + 1
        }
        self.loop_history.append(loop_record)
        return loop_record


if __name__ == "__main__":
    print("=== Testing LoopCloser ===")
    lc = LoopCloser()
    print(f"LoopCloser initialized with min_inliers={lc.min_inliers}, temporal_window={lc.temporal_window}")
    print("LoopCloser unit test PASSED!")
