"""
Top-Level Navigation Engine Orchestrator (P3 Module).
=====================================================
Unified interface matching the exact data contract defined in info.md:
  - Consumes single synchronized `SensorPacket` per frame (Camera image/path + IMU).
  - Orchestrates INS Dead Reckoning, Visual Odometry, Scale Estimation, and 15-State EKF.
  - Outputs standardized `EstimatedPose` packet for P4 Backend & React Dashboard.
"""

from typing import Dict, Any, Union, Optional
import os
import numpy as np
import cv2

from navigation.ins.imu_integrator import IMUIntegrator
from navigation.visual_odometry.vo_estimator import VisualOdometryEstimator
from navigation.visual_odometry.scale_estimator import ScaleEstimator
from navigation.fusion.ekf_fusion import EKFFusion
from navigation.utils.math_utils import quaternion_to_euler


class NavigationEngine:
    """
    Unified GPS-Denied Navigation Engine.
    Exposes process_packet() matching the exact data contract in info.md.
    """

    def __init__(
        self,
        camera_matrix: Optional[np.ndarray] = None,
        init_pos: Optional[np.ndarray] = None,
        init_vel: Optional[np.ndarray] = None,
        init_quat: Optional[np.ndarray] = None
    ):
        # 1. Visual Odometry & Metric Scale Estimator
        self.vo = VisualOdometryEstimator(camera_matrix=camera_matrix, min_inliers=6)
        self.scale_estimator = ScaleEstimator(default_scale=0.067, alpha=0.20)

        # 2. 15-State Extended Kalman Filter
        self.ekf = EKFFusion(init_pos=init_pos, init_vel=init_vel, init_quat=init_quat)

        self.prev_timestamp: Optional[float] = None
        self.last_known_altitude: Optional[float] = None

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

        Returns Standardized Output Schema (matches info.md):
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
          "confidence": float
        }
        """
        frame_id = packet.get("frame_id", 0)
        timestamp = float(packet.get("timestamp", 0.0))

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

        # 8. Format Exact Output Schema for P4 Dashboard
        pos = ekf_state["position"]
        vel = ekf_state["velocity"]
        euler_rad = ekf_state["orientation_euler"]  # [roll, pitch, yaw] in radians
        # Convert Euler to degrees for intuitive dashboard display (as shown in info.md)
        euler_deg = np.degrees(euler_rad)

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
            "confidence": round(float(confidence), 3)
        }

    @staticmethod
    def _parse_vector3(vec_input: Union[Dict[str, float], list, np.ndarray]) -> np.ndarray:
        """Helper to parse {x, y, z} dicts or [x, y, z] lists into np.ndarray."""
        if isinstance(vec_input, dict):
            return np.array([
                float(vec_input.get("x", 0.0)),
                float(vec_input.get("y", 0.0)),
                float(vec_input.get("z", 0.0))
            ], dtype=np.float64)
        return np.array(vec_input, dtype=np.float64)

    @staticmethod
    def _load_camera_frame(camera_data: Union[Dict[str, Any], np.ndarray]) -> Optional[np.ndarray]:
        """Loads camera frame from in-memory array or file path."""
        if isinstance(camera_data, np.ndarray):
            return camera_data

        if isinstance(camera_data, dict):
            if "frame" in camera_data and camera_data["frame"] is not None:
                return camera_data["frame"]
            if "image_path" in camera_data and camera_data["image_path"]:
                path = camera_data["image_path"]
                if os.path.exists(path):
                    return cv2.imread(path)
        return None


if __name__ == "__main__":
    print("=== Testing NavigationEngine with info.md SensorPacket ===")
    from navigation.utils.mock_generator import MockDataGenerator

    # 1. Initialize Engine
    engine = NavigationEngine()

    # 2. Simulate streaming packets from Blender
    gen = MockDataGenerator(trajectory_type="circular", duration=1.0, imu_hz=30, camera_hz=30)

    sample_output = None
    packet_count = 0

    for sensor_type, packet in gen.stream_dataset():
        if sensor_type == "camera":
            packet_count += 1
            # Format SensorPacket matching info.md
            gt = packet["ground_truth"]
            sensor_packet = {
                "frame_id": packet_count,
                "timestamp": packet["timestamp"],
                "camera": {
                    "frame": packet["frame"],
                    "width": 1280,
                    "height": 720
                },
                "imu": {
                    "acceleration": {
                        "x": float(gt["acceleration"][0]),
                        "y": float(gt["acceleration"][1]),
                        "z": float(gt["acceleration"][2] + 9.81)
                    },
                    "gyroscope": {
                        "x": float(gt["angular_velocity"][0]),
                        "y": float(gt["angular_velocity"][1]),
                        "z": float(gt["angular_velocity"][2])
                    }
                }
            }

            out = engine.process_packet(sensor_packet)
            sample_output = out

            if packet_count % 10 == 0:
                print(f"Frame #{out['frame_id']:02d} @ t={out['timestamp']:.2f}s | Pose: {out['estimated_pose']} | State: {out['tracking_state']} | Conf: {out['confidence']}")

    print("\n--- Final Sample Output (Sent to P4 Dashboard) ---")
    import json
    print(json.dumps(sample_output, indent=2))
    assert "estimated_pose" in sample_output
    assert "velocity" in sample_output
    assert "tracking_state" in sample_output
    assert "confidence" in sample_output
    print("\nNavigationEngine integration test PASSED! [info.md fully matched]")
