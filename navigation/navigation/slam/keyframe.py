"""
KeyFrame Module for Visual SLAM (P3 Module).
============================================
Represents a reference camera viewpoint in the persistent SLAM map:
  - Stores 6-DOF camera pose T_wc (4x4 transformation matrix).
  - Stores 2D keypoints and 256-bit binary ORB descriptors.
  - Maintains associations to 3D MapPoints.
  - Manages Covisibility Graph connections with other keyframes.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import cv2

from navigation.utils.math_utils import invert_transform_matrix, rotation_matrix_to_quaternion, quaternion_to_euler


class KeyFrame:
    """
    KeyFrame in the Visual SLAM Map.
    """

    _next_id = 0

    def __init__(
        self,
        frame_id: int,
        timestamp: float,
        pose_wc: np.ndarray,
        keypoints: List[cv2.KeyPoint],
        descriptors: np.ndarray
    ):
        self.id = KeyFrame._next_id
        KeyFrame._next_id += 1

        self.frame_id = int(frame_id)
        self.timestamp = float(timestamp)
        self.pose_wc = np.array(pose_wc, dtype=np.float64)  # Camera to World [R_wc | p_wc]
        self.pose_cw = invert_transform_matrix(self.pose_wc) # World to Camera [R_cw | t_cw]

        self.keypoints = keypoints
        self.descriptors = descriptors
        self.num_features = len(keypoints) if keypoints is not None else 0

        # Associations: keypoint index (0..N-1) -> MapPoint object
        self.map_points: Dict[int, Any] = {}

        # Covisibility Graph: target KeyFrame -> count of shared 3D MapPoints
        self.connected_keyframes: Dict['KeyFrame', int] = {}

    @property
    def position(self) -> np.ndarray:
        """Camera optical center in world frame p_wc."""
        return self.pose_wc[:3, 3]

    @property
    def rotation(self) -> np.ndarray:
        """Camera rotation matrix R_wc."""
        return self.pose_wc[:3, :3]

    def add_map_point(self, kp_idx: int, map_point: Any):
        """Associates a 2D keypoint with a 3D MapPoint."""
        self.map_points[kp_idx] = map_point

    def get_map_point(self, kp_idx: int) -> Optional[Any]:
        return self.map_points.get(kp_idx)

    def add_connection(self, other_kf: 'KeyFrame', shared_count: int):
        """Adds or updates a covisibility connection to another keyframe."""
        if other_kf != self and shared_count > 0:
            self.connected_keyframes[other_kf] = shared_count

    def remove_connection(self, other_kf: 'KeyFrame'):
        if other_kf in self.connected_keyframes:
            del self.connected_keyframes[other_kf]

    def get_covisible_keyframes(self, min_shared: int = 15, max_results: int = 5) -> List['KeyFrame']:
        """Returns the top connected keyframes sorted by shared landmark count."""
        candidates = [
            (kf, count) for kf, count in self.connected_keyframes.items()
            if count >= min_shared
        ]
        candidates.sort(key=lambda item: item[1], reverse=True)
        return [kf for kf, _ in candidates[:max_results]]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes KeyFrame metadata."""
        quat = rotation_matrix_to_quaternion(self.rotation)
        roll, pitch, yaw = quaternion_to_euler(quat)
        return {
            "keyframe_id": self.id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "position": self.position.tolist(),
            "orientation_euler": [roll, pitch, yaw],
            "num_features": self.num_features,
            "num_map_points": len(self.map_points),
            "num_connections": len(self.connected_keyframes)
        }


if __name__ == "__main__":
    print("=== Testing KeyFrame ===")
    T1 = np.eye(4)
    T1[:3, 3] = [1.0, 2.0, 3.0]

    kf1 = KeyFrame(frame_id=1, timestamp=0.033, pose_wc=T1, keypoints=[], descriptors=np.empty((0, 32)))
    self_pos = kf1.position
    print(f"KeyFrame #{kf1.id} Position: {self_pos}")
    assert np.allclose(self_pos, [1.0, 2.0, 3.0])
    print("KeyFrame test PASSED!")
