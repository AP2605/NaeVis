"""
Top-Level Navigation Engine Orchestrator (P3 Module).
=====================================================
Unified interface matching the exact data contract defined in info.md & to_see.md:
  - Consumes single synchronized `SensorPacket` per frame (Camera image/path + IMU).
  - Orchestrates INS Dead Reckoning, Visual Odometry, Scale Estimation, and 15-State EKF.
  - Generates autonomous 3D Waypoint Guidance & Steering Commands for Blender (P2).
  - Outputs standardized `EstimatedPose` and `FlightCommand` for P4 Backend & React Dashboard.
"""

from typing import Dict, Any, Union, Optional, List
import os
import time
import numpy as np
import cv2

from navigation.ins.imu_integrator import IMUIntegrator
from navigation.visual_odometry.vo_estimator import VisualOdometryEstimator
from navigation.visual_odometry.scale_estimator import ScaleEstimator
from navigation.fusion.ekf_fusion import EKFFusion
from navigation.guidance.waypoint_navigator import WaypointNavigator, Waypoint
from navigation.utils.math_utils import quaternion_to_euler


class NavigationEngine:
    """
    Unified GPS-Denied Navigation & Autonomous Flight Guidance Engine.
    Exposes process_packet() matching the exact data contract in info.md.
    """

    def __init__(
        self,
        camera_matrix: Optional[np.ndarray] = None,
        waypoints: Optional[List[Union[Dict[str, Any], Waypoint]]] = None,
        init_pos: Optional[np.ndarray] = None,
        init_vel: Optional[np.ndarray] = None,
        init_quat: Optional[np.ndarray] = None
    ):
        # 1. Visual Odometry & Metric Scale Estimator
        self.vo = VisualOdometryEstimator(camera_matrix=camera_matrix, min_inliers=6)
        self.scale_estimator = ScaleEstimator(default_scale=0.067, alpha=0.20)

        # 2. 15-State Extended Kalman Filter
        self.ekf = EKFFusion(init_pos=init_pos, init_vel=init_vel, init_quat=init_quat)

        # 3. Waypoint Guidance & Steering Controller
        self.guidance = WaypointNavigator(waypoints=waypoints)

        self.prev_timestamp: Optional[float] = None

    def load_waypoints(self, filepath: str) -> bool:
        """Loads mission waypoints from a JSON file."""
        return self.guidance.load_waypoints_from_file(filepath)

    def set_waypoints(self, waypoint_list: List[Union[Dict[str, Any], Waypoint]]):
        """Sets mission waypoints dynamically."""
        self.guidance.set_waypoints(waypoint_list)

    def process_packet(self, packet: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a single incoming SensorPacket from P2 (Blender / Simulator).

        Expected Input Schema (matches info.md):
        {
          "frame_id": int,
          "timestamp": float,
          "camera": {
            "image_path": str (optional) or "frame": np.ndarray,
            "width": int,
            "height": int
          },
          "imu": {
            "acceleration": {"x": float, "y": float, "z": float} or [ax, ay, az],
            "gyroscope": {"x": float, "y": float, "z": float} or [gx, gy, gz]
          }
        }

        Returns Standardized Output Schema (matches info.md & to_see.md):
        {
          "frame_id": int,
          "timestamp": float,
          "estimated_pose": {
            "x": float, "y": float, "z": float,
            "roll": float, "pitch": float, "yaw": float
          },
          "velocity": {
            "x": float, "y": float, "z": float
          },
          "tracking_state": str,
          "confidence": float,
          "flight_command": {
            "desired_velocity_mps": float,
            "target_heading_yaw_deg": float,
            "climb_rate_mps": float,
            "active_waypoint_idx": int,
            "distance_to_waypoint_m": float,
            "mission_status": str
          }
        }
        """
        t_start = time.perf_counter()
        frame_id = packet.get("frame_id", 0)
        timestamp = float(packet.get("timestamp", 0.0))

        # Check for dynamic waypoints passed inside packet
        if "mission_waypoints" in packet and packet["mission_waypoints"]:
            self.guidance.set_waypoints(packet["mission_waypoints"])

        # Compute dt
        if self.prev_timestamp is None:
            dt = 0.0333  # ~30 FPS default for first frame
        else:
            dt = max(timestamp - self.prev_timestamp, 1e-4)
        self.prev_timestamp = timestamp

        # 1. Parse IMU Data
        imu_data = packet.get("imu", {})
        accel = self._parse_vector3(imu_data.get("acceleration", imu_data.get("accel", [0.0, 0.0, 9.81])))
        gyro = self._parse_vector3(imu_data.get("gyroscope", imu_data.get("gyro", [0.0, 0.0, 0.0])))

        # 2. EKF Prediction Step (Driven by IMU)
        ekf_state = self.ekf.predict(accel, gyro, dt=dt)

        # 3. Buffer IMU acceleration & velocity into Scale Estimator
        linear_acc_world = ekf_state["rotation_matrix"] @ (accel - ekf_state["accel_bias"]) + self.ekf.gravity_world
        self.scale_estimator.add_imu_sample(linear_acc_world, ekf_state["velocity"], dt=dt)

        # 4. Parse Camera Image
        camera_data = packet.get("camera", {})
        frame = self._load_camera_frame(camera_data)

        tracking_state = "PREDICTING_IMU_ONLY"
        confidence = 0.50

        if frame is not None:
            # 5. Compute Metric Scale
            current_scale = self.scale_estimator.get_current_scale()

            # 6. Visual Odometry Step
            vo_res = self.vo.process_frame(frame, scale=current_scale)
            tracking_state = vo_res["tracking_state"]
            confidence = vo_res["confidence"]

            # Update scale estimator with VO unit translation
            if vo_res["num_inliers"] >= 6:
                unit_t = vo_res["relative_t"] / max(1e-6, np.linalg.norm(vo_res["relative_t"]))
                self.scale_estimator.estimate_scale(unit_t, dt=dt)

                # 7. EKF Measurement Update Step (Driven by VO)
                ekf_state = self.ekf.update_vo_pose(
                    pos_vo=vo_res["position"],
                    quat_vo=vo_res["orientation_quat"],
                    confidence=confidence
                )
        elif "sim_position" in packet and packet["sim_position"] is not None:
            sim_pos = self._parse_vector3(packet["sim_position"])
            ekf_state["position"] = sim_pos
            tracking_state = "SIMULATION_TRACKING"
            confidence = 0.98

        # 8. Compute Autonomous Flight Steering Command for Blender
        pos = ekf_state["position"]
        vel = ekf_state["velocity"]
        euler_rad = ekf_state["orientation_euler"]  # [roll, pitch, yaw] in radians
        euler_deg = np.degrees(euler_rad)

        flight_command = self.guidance.compute_flight_command(
            current_pos=pos,
            current_yaw_deg=float(euler_deg[2]),
            dt=dt
        )

        # 9. Measure Processing Time
        processing_time_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

        return {
            "frame_id": frame_id,
            "timestamp": round(timestamp, 4),
            "estimated_pose": {
                "x": round(float(pos[0]), 4),
                "y": round(float(pos[1]), 4),
                "z": round(float(pos[2]), 4),
                "roll": round(float(euler_deg[0]), 2),
                "pitch": round(float(euler_deg[1]), 2),
                "yaw": round(float(euler_deg[2]), 2)
            },
            "velocity": {
                "x": round(float(vel[0]), 4),
                "y": round(float(vel[1]), 4),
                "z": round(float(vel[2]), 4)
            },
            "tracking_state": tracking_state,
            "confidence": round(float(confidence), 3),
            "processing_time_ms": processing_time_ms,
            "flight_command": flight_command
        }

    @staticmethod
    def _parse_vector3(vec_input: Union[Dict[str, float], list, np.ndarray]) -> np.ndarray:
        if isinstance(vec_input, dict):
            return np.array([
                float(vec_input.get("x", 0.0)),
                float(vec_input.get("y", 0.0)),
                float(vec_input.get("z", 0.0))
            ], dtype=np.float64)
        return np.array(vec_input, dtype=np.float64)

    @staticmethod
    def _load_camera_frame(camera_data: Union[Dict[str, Any], np.ndarray]) -> Optional[np.ndarray]:
        if isinstance(camera_data, np.ndarray):
            return camera_data

        if isinstance(camera_data, dict):
            if "frame" in camera_data and camera_data["frame"] is not None:
                return camera_data["frame"]
            if "image_base64" in camera_data and camera_data["image_base64"]:
                try:
                    import base64
                    img_bytes = base64.b64decode(camera_data["image_base64"])
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    pass
            if "image_path" in camera_data and camera_data["image_path"]:
                path = camera_data["image_path"]
                if os.path.exists(path):
                    return cv2.imread(path)
        return None


if __name__ == "__main__":
    print("=== Testing NavigationEngine with Waypoint Guidance ===")
    engine = NavigationEngine(waypoints=[
        {"id": 1, "name": "Takeoff", "x": 0.0, "y": 0.0, "z": 5.0, "speed": 2.0},
        {"id": 2, "name": "Target_A", "x": 10.0, "y": 5.0, "z": 6.0, "speed": 3.5}
    ])

    dummy_packet = {
        "frame_id": 1,
        "timestamp": 0.033,
        "camera": {"frame": np.zeros((720, 1280, 3), dtype=np.uint8)},
        "imu": {"acceleration": [0, 0, 9.81], "gyroscope": [0, 0, 0]}
    }

    res = engine.process_packet(dummy_packet)
    print(f"Output with Flight Command: {res['flight_command']}")
    assert "flight_command" in res
    assert res["flight_command"]["active_waypoint_idx"] == 1
    print("NavigationEngine guidance test PASSED!")
