"""
3D MapPoint Landmark Module for Visual SLAM (P3 Module).
========================================================
Represents a physical 3D world landmark:
  - 3D spatial coordinate P_w = [X, Y, Z] in world frame.
  - Multi-view observations across multiple KeyFrames.
  - Representative 256-bit binary ORB descriptor.
  - Geometric reprojection error validation.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import cv2


class MapPoint:
    """
    3D MapPoint Landmark in the Visual SLAM Map.
    """

    _next_id = 0

    def __init__(
        self,
        pos_world: np.ndarray,
        descriptor: Optional[np.ndarray] = None,
        first_keyframe: Optional[Any] = None,
        first_kp_idx: int = -1
    ):
        self.id = MapPoint._next_id
        MapPoint._next_id += 1

        self.pos_world = np.array(pos_world, dtype=np.float64)  # [X, Y, Z] in meters
        self.descriptor = descriptor.copy() if descriptor is not None else np.zeros(32, dtype=np.uint8)

        # Observations: KeyFrame -> keypoint index (int)
        self.observations: Dict[Any, int] = {}
        if first_keyframe is not None and first_kp_idx >= 0:
            self.observations[first_keyframe] = first_kp_idx
            first_keyframe.add_map_point(first_kp_idx, self)

        self.viewing_direction = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        self.is_bad = False
        self.reprojection_errors: List[float] = []

    def add_observation(self, keyframe: Any, kp_idx: int):
        """Adds a multi-view observation of this landmark in a KeyFrame."""
        self.observations[keyframe] = kp_idx
        keyframe.add_map_point(kp_idx, self)

    def remove_observation(self, keyframe: Any):
        """Removes observation and marks bad if fewer than 2 views remain."""
        if keyframe in self.observations:
            del self.observations[keyframe]
        if len(self.observations) < 2:
            self.is_bad = True

    @property
    def num_observations(self) -> int:
        return len(self.observations)

    def get_reprojection_error(self, keyframe: Any, K: np.ndarray) -> float:
        """
        Calculates the Euclidean reprojection error in pixels between
        the projected 3D landmark and the 2D keypoint in the KeyFrame.
        """
        if keyframe not in self.observations:
            return float("inf")

        kp_idx = self.observations[keyframe]
        kp = keyframe.keypoints[kp_idx]
        u_obs, v_obs = kp.pt

        # Transform point from World to Camera frame: P_c = R_cw * P_w + t_cw
        R_cw = keyframe.pose_cw[:3, :3]
        t_cw = keyframe.pose_cw[:3, 3]
        p_c = R_cw @ self.pos_world + t_cw

        # Must be in front of the camera
        if p_c[2] < 0.1:
            return float("inf")

        # Project using camera intrinsics K
        u_proj = (K[0, 0] * p_c[0] / p_c[2]) + K[0, 2]
        v_proj = (K[1, 1] * p_c[1] / p_c[2]) + K[1, 2]

        err = float(np.sqrt((u_obs - u_proj) ** 2 + (v_obs - v_proj) ** 2))
        return err

    def is_visible_in(
        self,
        keyframe: Any,
        K: np.ndarray,
        img_w: int = 1280,
        img_h: int = 720,
        margin: int = 10
    ) -> Tuple[bool, float, float]:
        """
        Checks whether this 3D landmark projects into the field of view of a given camera.
        Returns: (is_visible, projected_u, projected_v)
        """
        R_cw = keyframe.pose_cw[:3, :3]
        t_cw = keyframe.pose_cw[:3, 3]
        p_c = R_cw @ self.pos_world + t_cw

        if p_c[2] < 0.2:
            return False, 0.0, 0.0

        u = (K[0, 0] * p_c[0] / p_c[2]) + K[0, 2]
        v = (K[1, 1] * p_c[1] / p_c[2]) + K[1, 2]

        is_vis = (margin <= u < img_w - margin) and (margin <= v < img_h - margin)
        return is_vis, float(u), float(v)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.id,
            "position": self.pos_world.tolist(),
            "num_observations": self.num_observations,
            "is_bad": self.is_bad
        }


if __name__ == "__main__":
    print("=== Testing MapPoint ===")
    p_3d = np.array([0.5, 0.2, 5.0])
    mp = MapPoint(pos_world=p_3d)

    print(f"MapPoint #{mp.id} Created at: {mp.pos_world}")
    assert np.allclose(mp.pos_world, [0.5, 0.2, 5.0])
    assert mp.num_observations == 0
    print("MapPoint test PASSED!")
