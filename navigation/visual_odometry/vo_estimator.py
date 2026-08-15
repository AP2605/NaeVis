"""
Visual Odometry (VO) Estimator Module (P3 Module).
==================================================
Estimates frame-to-frame 6-DOF camera motion and accumulates world trajectory:
  - Computes Essential Matrix (E) with RANSAC outlier filtering.
  - Decomposes E into relative rotation matrix (R) and unit translation direction (t).
  - Handles scale integration, inlier ratio tracking, and tracking confidence scoring.
  - Supports 1280x720 HD Blender drone camera intrinsics.
"""

from typing import Dict, Any, Tuple, Optional, List
import numpy as np
import cv2

from navigation.visual_odometry.orb_tracker import ORBTracker
from navigation.utils.math_utils import (
    rotation_matrix_to_quaternion,
    quaternion_to_euler,
    create_transform_matrix,
    invert_transform_matrix
)


class VisualOdometryEstimator:
    """
    Monocular Feature-Based Visual Odometry Estimator.
    Accumulates 3D camera trajectory from consecutive camera frames.
    """

    def __init__(
        self,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
        n_features: int = 2000,
        ransac_prob: float = 0.999,
        ransac_threshold: float = 2.5,
        min_inliers: int = 6
    ):
        # Default camera intrinsics (1280x720 HD Blender Drone spec) if none provided
        if camera_matrix is not None:
            self.K = np.array(camera_matrix, dtype=np.float64)
        else:
            self.K = np.array([
                [800.0,   0.0, 640.0],
                [  0.0, 800.0, 360.0],
                [  0.0,   0.0,   1.0]
            ], dtype=np.float64)

        self.dist_coeffs = np.array(dist_coeffs, dtype=np.float64) if dist_coeffs is not None else None

        self.ransac_prob = ransac_prob
        self.ransac_threshold = ransac_threshold
        self.min_inliers = min_inliers

        self.tracker = ORBTracker(
            n_features=n_features,
            scale_factor=1.2,
            n_levels=8,
            ratio_threshold=0.80,
            fast_threshold=10
        )

        # Previous frame cache
        self.prev_frame: Optional[np.ndarray] = None
        self.prev_kp: List[cv2.KeyPoint] = []
        self.prev_des: Optional[np.ndarray] = None

        # Cumulative 4x4 World Transformation Matrix T_wc = [R_wc | p_wc]
        self.current_pose_wc = np.eye(4, dtype=np.float64)
        self.frame_idx = 0

    def process_frame(self, frame: np.ndarray, scale: float = 1.0) -> Dict[str, Any]:
        """
        Processes a single camera frame and returns estimated relative motion and world pose.

        Args:
            frame: Camera image (BGR or Grayscale).
            scale: Metric scale factor (meters) for relative translation.

        Returns:
            Dictionary containing position, orientation, relative R/t, inliers, and tracking state.
        """
        self.frame_idx += 1

        # 1. Feature Extraction
        kp, des = self.tracker.detect_and_compute(frame)

        # Handle Initial Frame
        if self.prev_des is None or des is None or len(kp) < 10:
            self.prev_frame = frame
            self.prev_kp = kp
            self.prev_des = des

            pos = self.current_pose_wc[:3, 3]
            quat = rotation_matrix_to_quaternion(self.current_pose_wc[:3, :3])
            roll, pitch, yaw = quaternion_to_euler(quat)

            return {
                "frame_idx": self.frame_idx,
                "tracking_state": "INITIALIZING",
                "position": pos.copy(),
                "orientation_quat": quat.copy(),
                "orientation_euler": np.array([roll, pitch, yaw]),
                "relative_R": np.eye(3),
                "relative_t": np.zeros(3),
                "num_inliers": 0,
                "num_matches": 0,
                "confidence": 0.0,
                "matched_pts_prev": np.empty((0, 2)),
                "matched_pts_curr": np.empty((0, 2))
            }

        # 2. Feature Matching with Previous Frame
        pts_prev, pts_curr, good_matches = self.tracker.match(self.prev_des, des, self.prev_kp, kp)

        if len(good_matches) < 6:
            # Tracking loss / insufficient matches
            pos = self.current_pose_wc[:3, 3]
            quat = rotation_matrix_to_quaternion(self.current_pose_wc[:3, :3])
            roll, pitch, yaw = quaternion_to_euler(quat)

            self.prev_frame = frame
            self.prev_kp = kp
            self.prev_des = des

            return {
                "frame_idx": self.frame_idx,
                "tracking_state": "INSUFFICIENT_FEATURES",
                "position": pos.copy(),
                "orientation_quat": quat.copy(),
                "orientation_euler": np.array([roll, pitch, yaw]),
                "relative_R": np.eye(3),
                "relative_t": np.zeros(3),
                "num_inliers": 0,
                "num_matches": len(good_matches),
                "confidence": 0.0,
                "matched_pts_prev": pts_prev,
                "matched_pts_curr": pts_curr
            }

        # 3. Essential Matrix Estimation via RANSAC
        E, inlier_mask = cv2.findEssentialMat(
            pts_prev,
            pts_curr,
            self.K,
            method=cv2.RANSAC,
            prob=self.ransac_prob,
            threshold=self.ransac_threshold
        )

        if E is None or inlier_mask is None:
            num_inliers = 0
            R_rel = np.eye(3)
            t_rel = np.zeros(3)
            tracking_state = "ESSENTIAL_MATRIX_FAILED"
            confidence = 0.0
        else:
            # 4. Pose Recovery from Essential Matrix
            inliers, R_rel, t_rel, mask_pose = cv2.recoverPose(
                E, pts_prev, pts_curr, self.K, mask=inlier_mask.copy()
            )
            num_inliers = int(inliers)

            if num_inliers >= self.min_inliers:
                tracking_state = "TRACKING_GOOD"
                t_scaled = t_rel.flatten() * scale

                T_rel = create_transform_matrix(R_rel, t_scaled)
                self.current_pose_wc = self.current_pose_wc @ T_rel

                inlier_ratio = num_inliers / max(1, len(good_matches))
                confidence = float(np.clip(min(1.0, num_inliers / 25.0) * inlier_ratio, 0.0, 1.0))
            else:
                tracking_state = "TRACKING_POOR"
                R_rel = np.eye(3)
                t_rel = np.zeros(3)
                confidence = 0.1

        # Update cache for next iteration
        self.prev_frame = frame
        self.prev_kp = kp
        self.prev_des = des

        pos = self.current_pose_wc[:3, 3]
        quat = rotation_matrix_to_quaternion(self.current_pose_wc[:3, :3])
        roll, pitch, yaw = quaternion_to_euler(quat)

        return {
            "frame_idx": self.frame_idx,
            "tracking_state": tracking_state,
            "position": pos.copy(),
            "orientation_quat": quat.copy(),
            "orientation_euler": np.array([roll, pitch, yaw]),
            "relative_R": R_rel,
            "relative_t": t_rel,
            "num_inliers": num_inliers,
            "num_matches": len(good_matches),
            "confidence": confidence,
            "matched_pts_prev": pts_prev,
            "matched_pts_curr": pts_curr
        }

    def reset_pose(self, pose_4x4: Optional[np.ndarray] = None):
        """Resets the accumulated camera pose (e.g. for loop closure correction)."""
        self.current_pose_wc = np.array(pose_4x4 if pose_4x4 is not None else np.eye(4), dtype=np.float64)
        self.prev_des = None


if __name__ == "__main__":
    print("=== Testing VisualOdometryEstimator (1280x720 HD) ===")
    from navigation.utils.mock_generator import MockDataGenerator

    gen = MockDataGenerator(trajectory_type="circular", duration=2.0, camera_hz=30)
    vo = VisualOdometryEstimator(ransac_threshold=2.5, min_inliers=6)

    frame_count = 0
    inliers_list = []
    confidence_list = []

    for sensor_type, packet in gen.stream_dataset():
        if sensor_type == "camera":
            frame_count += 1
            vo_output = vo.process_frame(packet["frame"], scale=0.1)
            inliers_list.append(vo_output["num_inliers"])
            confidence_list.append(vo_output["confidence"])

            if frame_count % 10 == 0:
                pos = vo_output["position"]
                print(f"Frame #{vo_output['frame_idx']:02d}: State={vo_output['tracking_state']}, Inliers={vo_output['num_inliers']}, Conf={vo_output['confidence']:.2f}, Est Pos=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]")

    print(f"\nProcessed {frame_count} 720p frames.")
    avg_inliers = np.mean(inliers_list[1:])
    avg_conf = np.mean(confidence_list[1:])
    print(f"Average Inliers: {avg_inliers:.1f}")
    print(f"Average Confidence: {avg_conf:.3f}")

    assert avg_inliers >= 10, f"Expected average inliers >= 10, got {avg_inliers}"
    print("VisualOdometryEstimator update PASSED successfully!")
