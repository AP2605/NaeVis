"""
Fake Data Generator for Navigation & Localization Testing (P3 Module).
=======================================================================
Generates synchronized synthetic sensor streams for GPS-denied navigation testing:
  1. High-rate 6-axis IMU data (Accelerometer + Gyroscope with noise and bias).
  2. Medium-rate Camera data (1280x720 RGB frames with rendered 3D landmarks for real ORB feature detection).
  3. Millimeter-accurate Ground Truth trajectory (Position, Velocity, Orientation, Angular Velocity).

Matches the Blender Simulation specification (1280x720 PNGs, frame_000001.png, JSON/CSV logs).
"""

import os
import json
import math
import time
from typing import Dict, Any, Generator, Tuple, List, Optional
import numpy as np
import cv2


class SyntheticTrajectory:
    """
    Computes analytical ground-truth kinematic states (position, velocity,
    acceleration, orientation, and angular velocity) for parameterized flight paths.
    """

    def __init__(self, trajectory_type: str = "figure_eight", duration: float = 30.0, radius: float = 10.0, speed: float = 2.0):
        self.trajectory_type = trajectory_type
        self.duration = duration
        self.radius = radius
        self.speed = speed
        self.omega = self.speed / self.radius if self.radius > 0 else 0.5

    def get_state(self, t: float) -> Dict[str, Any]:
        """
        Returns ground-truth kinematic state at time t in world frame (East-North-Up / ENU).
        """
        t_clamped = min(max(t, 0.0), self.duration)

        if self.trajectory_type == "circular":
            theta = self.omega * t_clamped
            pos = np.array([
                self.radius * np.cos(theta),
                self.radius * np.sin(theta),
                5.0 + 0.5 * np.sin(0.2 * theta)
            ], dtype=np.float64)

            vel = np.array([
                -self.radius * self.omega * np.sin(theta),
                self.radius * self.omega * np.cos(theta),
                0.1 * self.omega * np.cos(0.2 * theta)
            ], dtype=np.float64)

            acc = np.array([
                -self.radius * (self.omega ** 2) * np.cos(theta),
                -self.radius * (self.omega ** 2) * np.sin(theta),
                -0.02 * (self.omega ** 2) * np.sin(0.2 * theta)
            ], dtype=np.float64)

            yaw = theta + np.pi / 2.0
            roll = 0.05 * np.sin(theta)
            pitch = 0.02 * np.cos(theta)
            ang_vel = np.array([0.0, 0.0, self.omega], dtype=np.float64)

        elif self.trajectory_type == "figure_eight":
            w = self.omega
            a = self.radius

            pos = np.array([
                a * np.sin(w * t_clamped),
                (a / 2.0) * np.sin(2.0 * w * t_clamped),
                5.0 + 1.5 * np.sin(w * t_clamped)
            ], dtype=np.float64)

            vel = np.array([
                a * w * np.cos(w * t_clamped),
                a * w * np.cos(2.0 * w * t_clamped),
                1.5 * w * np.cos(w * t_clamped)
            ], dtype=np.float64)

            acc = np.array([
                -a * (w ** 2) * np.sin(w * t_clamped),
                -2.0 * a * (w ** 2) * np.sin(2.0 * w * t_clamped),
                -1.5 * (w ** 2) * np.sin(w * t_clamped)
            ], dtype=np.float64)

            yaw = math.atan2(vel[1], vel[0]) if (vel[0]**2 + vel[1]**2) > 1e-4 else 0.0
            roll = 0.08 * np.sin(2 * w * t_clamped)
            pitch = 0.04 * np.cos(w * t_clamped)

            dt_eps = 1e-3
            vel_next = np.array([
                a * w * np.cos(w * (t_clamped + dt_eps)),
                a * w * np.cos(2.0 * w * (t_clamped + dt_eps)),
                1.5 * w * np.cos(w * (t_clamped + dt_eps))
            ])
            yaw_next = math.atan2(vel_next[1], vel_next[0])
            yaw_rate = (yaw_next - yaw) / dt_eps
            ang_vel = np.array([0.0, 0.0, yaw_rate], dtype=np.float64)

        elif self.trajectory_type == "straight_line":
            t_acc = self.duration * 0.2
            t_dec = self.duration * 0.8
            max_v = self.speed

            if t_clamped < t_acc:
                a_x = max_v / t_acc
                v_x = a_x * t_clamped
                x_pos = 0.5 * a_x * (t_clamped ** 2)
            elif t_clamped < t_dec:
                a_x = 0.0
                v_x = max_v
                x_pos = 0.5 * max_v * t_acc + max_v * (t_clamped - t_acc)
            else:
                a_x = -max_v / (self.duration - t_dec)
                dt_d = t_clamped - t_dec
                v_x = max(0.0, max_v + a_x * dt_d)
                x_pos = 0.5 * max_v * t_acc + max_v * (t_dec - t_acc) + max_v * dt_d + 0.5 * a_x * (dt_d ** 2)

            pos = np.array([x_pos, 0.0, 4.0], dtype=np.float64)
            vel = np.array([v_x, 0.0, 0.0], dtype=np.float64)
            acc = np.array([a_x, 0.0, 0.0], dtype=np.float64)
            roll, pitch, yaw = 0.0, 0.0, 0.0
            ang_vel = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        else:  # 'hover'
            pos = np.array([0.0, 0.0, 3.0], dtype=np.float64)
            vel = np.array([0.0, 0.0, 0.0], dtype=np.float64)
            acc = np.array([0.0, 0.0, 0.0], dtype=np.float64)
            roll, pitch, yaw = 0.0, 0.0, 0.0
            ang_vel = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        R_wb = self._euler_to_rotation_matrix(roll, pitch, yaw)
        quat = self._rotation_matrix_to_quaternion(R_wb)

        return {
            "timestamp": t_clamped,
            "position": pos,
            "velocity": vel,
            "acceleration": acc,
            "orientation_euler": np.array([roll, pitch, yaw], dtype=np.float64),
            "orientation_quat": quat,  # [qw, qx, qy, qz]
            "rotation_matrix": R_wb,
            "angular_velocity": ang_vel
        }

    @staticmethod
    def _euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
        cr, sr = np.cos(roll), np.sin(roll)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cy, sy = np.cos(yaw), np.sin(yaw)

        R_z = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        R_y = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
        R_x = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
        return R_z @ R_y @ R_x

    @staticmethod
    def _rotation_matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
        tr = np.trace(R)
        if tr > 0:
            S = np.sqrt(tr + 1.0) * 2
            qw = 0.25 * S
            qx = (R[2, 1] - R[1, 2]) / S
            qy = (R[0, 2] - R[2, 0]) / S
            qz = (R[1, 0] - R[0, 1]) / S
        elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
            S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
            qw = (R[2, 1] - R[1, 2]) / S
            qx = 0.25 * S
            qy = (R[0, 1] + R[1, 0]) / S
            qz = (R[0, 2] + R[2, 0]) / S
        elif R[1, 1] > R[2, 2]:
            S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
            qw = (R[0, 2] - R[2, 0]) / S
            qx = (R[0, 1] + R[1, 0]) / S
            qy = 0.25 * S
            qz = (R[1, 2] + R[2, 1]) / S
        else:
            S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
            qw = (R[1, 0] - R[0, 1]) / S
            qx = (R[0, 2] + R[2, 0]) / S
            qy = (R[1, 2] + R[2, 1]) / S
            qz = 0.25 * S
        q = np.array([qw, qx, qy, qz], dtype=np.float64)
        return q / np.linalg.norm(q)


class SyntheticIMU:
    """
    Simulates a 6-axis IMU (3-axis Accelerometer + 3-axis Gyroscope).
    """

    def __init__(
        self,
        accel_noise_std: float = 0.05,
        gyro_noise_std: float = 0.005,
        accel_bias: Optional[np.ndarray] = None,
        gyro_bias: Optional[np.ndarray] = None,
        gravity_magnitude: float = 9.81
    ):
        self.accel_noise_std = accel_noise_std
        self.gyro_noise_std = gyro_noise_std
        self.accel_bias = accel_bias if accel_bias is not None else np.array([0.02, -0.01, 0.03])
        self.gyro_bias = gyro_bias if gyro_bias is not None else np.array([0.001, -0.002, 0.001])
        self.gravity_world = np.array([0.0, 0.0, -gravity_magnitude], dtype=np.float64)

    def measure(self, ground_truth_state: Dict[str, Any]) -> Dict[str, Any]:
        R_wb = ground_truth_state["rotation_matrix"]
        acc_world = ground_truth_state["acceleration"]
        ang_vel_world = ground_truth_state["angular_velocity"]

        # Accelerometer specific force
        specific_force_world = acc_world - self.gravity_world
        specific_force_body = R_wb.T @ specific_force_world
        accel_noise = np.random.normal(0, self.accel_noise_std, 3)
        accel_measured = specific_force_body + self.accel_bias + accel_noise

        # Gyroscope angular rate
        ang_vel_body = R_wb.T @ ang_vel_world
        gyro_noise = np.random.normal(0, self.gyro_noise_std, 3)
        gyro_measured = ang_vel_body + self.gyro_bias + gyro_noise

        return {
            "timestamp": ground_truth_state["timestamp"],
            "accel": accel_measured,
            "gyro": gyro_measured,
            "accel_true_body": specific_force_body,
            "gyro_true_body": ang_vel_body,
            "accel_bias": self.accel_bias.copy(),
            "gyro_bias": self.gyro_bias.copy()
        }


class SyntheticCameraEnvironment:
    """
    Renders 1280x720 HD RGB frames with realistic perspective projection
    and high-contrast landmarks matching Blender drone camera specs.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        fx: float = 800.0,
        fy: float = 800.0,
        cx: float = 640.0,
        cy: float = 360.0,
        num_landmarks: int = 800,
        scene_bound: float = 30.0
    ):
        self.width = width
        self.height = height
        self.fx = fx
        self.fy = fy
        self.cx = cx
        self.cy = cy
        self.K = np.array([
            [fx, 0.0, cx],
            [0.0, fy, cy],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        np.random.seed(42)
        self.landmarks = []
        for _ in range(num_landmarks):
            lx = np.random.uniform(-scene_bound, scene_bound)
            ly = np.random.uniform(-scene_bound, scene_bound)
            lz = np.random.uniform(0.0, 8.0)
            color = (int(np.random.randint(50, 255)), int(np.random.randint(50, 255)), int(np.random.randint(50, 255)))
            size = int(np.random.randint(5, 12))
            self.landmarks.append({
                "pos_world": np.array([lx, ly, lz], dtype=np.float64),
                "color": color,
                "size": size,
                "shape": np.random.choice(["circle", "rect", "cross"])
            })

    def render_frame(self, ground_truth_state: Dict[str, Any]) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        R_wb = ground_truth_state["rotation_matrix"]
        p_wb = ground_truth_state["position"]

        # Optical camera frame: X-right, Y-down, Z-forward
        R_bc = np.array([
            [0, -1,  0],
            [0,  0, -1],
            [1,  0,  0]
        ], dtype=np.float64)

        R_wc = R_wb @ R_bc
        p_wc = p_wb

        R_cw = R_wc.T
        t_cw = -R_cw @ p_wc

        frame = np.full((self.height, self.width, 3), 40, dtype=np.uint8)

        # Background grid
        grid_step = 80
        for gx in range(0, self.width, grid_step):
            cv2.line(frame, (gx, 0), (gx, self.height), (55, 55, 55), 1)
        for gy in range(0, self.height, grid_step):
            cv2.line(frame, (0, gy), (self.width, gy), (55, 55, 55), 1)

        # Subtle noise
        noise = np.random.randint(0, 25, (self.height, self.width, 3), dtype=np.uint8)
        frame = cv2.add(frame, noise)

        visible_features = []

        for lm in self.landmarks:
            p_w = lm["pos_world"]
            p_c = R_cw @ p_w + t_cw

            if p_c[2] > 0.5:
                u = (self.fx * p_c[0] / p_c[2]) + self.cx
                v = (self.fy * p_c[1] / p_c[2]) + self.cy

                if 10 <= u < (self.width - 10) and 10 <= v < (self.height - 10):
                    px, py = int(u), int(v)
                    color = lm["color"]
                    sz = lm["size"]

                    if lm["shape"] == "circle":
                        cv2.circle(frame, (px, py), sz, color, -1)
                        cv2.circle(frame, (px, py), max(2, sz // 2), (255, 255, 255), -1)
                    elif lm["shape"] == "rect":
                        cv2.rectangle(frame, (px - sz, py - sz), (px + sz, py + sz), color, -1)
                        cv2.rectangle(frame, (px - sz // 2, py - sz // 2), (px + sz // 2, py + sz // 2), (0, 0, 0), -1)
                    else:
                        cv2.line(frame, (px - sz, py), (px + sz, py), (255, 255, 255), 2)
                        cv2.line(frame, (px, py - sz), (px, py + sz), (255, 255, 255), 2)

                    visible_features.append({
                        "pixel_pos": (u, v),
                        "depth": p_c[2],
                        "world_pos": p_w
                    })

        return frame, visible_features


class MockDataGenerator:
    """
    Main Mock Data Generator orchestrator.
    Produces 1280x720 HD Blender-compatible synthetic flight streams.
    """

    def __init__(
        self,
        trajectory_type: str = "figure_eight",
        duration: float = 20.0,
        imu_hz: int = 100,
        camera_hz: int = 30,
        add_sensor_noise: bool = True
    ):
        self.trajectory = SyntheticTrajectory(trajectory_type=trajectory_type, duration=duration)
        self.imu = SyntheticIMU(
            accel_noise_std=0.05 if add_sensor_noise else 0.0,
            gyro_noise_std=0.005 if add_sensor_noise else 0.0
        )
        self.camera = SyntheticCameraEnvironment(width=1280, height=720, fx=800.0, fy=800.0, cx=640.0, cy=360.0)
        self.duration = duration
        self.imu_dt = 1.0 / imu_hz
        self.cam_dt = 1.0 / camera_hz

    def stream_dataset(self) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        t = 0.0
        next_imu_time = 0.0
        next_cam_time = 0.0
        frame_id = 1

        while t <= self.duration:
            if next_imu_time <= next_cam_time:
                t = next_imu_time
                gt = self.trajectory.get_state(t)
                imu_data = self.imu.measure(gt)
                imu_data["frame_id"] = frame_id
                imu_data["ground_truth"] = gt
                yield ("imu", imu_data)
                next_imu_time += self.imu_dt
            else:
                t = next_cam_time
                gt = self.trajectory.get_state(t)
                frame, visible_lms = self.camera.render_frame(gt)
                cam_data = {
                    "frame_id": frame_id,
                    "timestamp": t,
                    "frame": frame,
                    "visible_landmarks": visible_lms,
                    "num_visible": len(visible_lms),
                    "camera_intrinsics": self.camera.K,
                    "ground_truth": gt
                }
                yield ("camera", cam_data)
                frame_id += 1
                next_cam_time += self.cam_dt

    def export_dataset_to_disk(self, output_dir: str):
        """
        Exports the dataset in Blender Simulation standard format:
          - images/frame_000001.png, frame_000002.png ...
          - imu.json & imu.csv
          - telemetry.json & ground_truth.csv
        """
        os.makedirs(output_dir, exist_ok=True)
        img_dir = os.path.join(output_dir, "images")
        os.makedirs(img_dir, exist_ok=True)

        imu_json_records = []
        telemetry_json_records = []

        imu_csv_path = os.path.join(output_dir, "imu.csv")
        gt_csv_path = os.path.join(output_dir, "ground_truth.csv")
        imu_json_path = os.path.join(output_dir, "imu.json")
        telemetry_json_path = os.path.join(output_dir, "telemetry.json")

        print(f"[MockDataGenerator] Exporting 1280x720 Blender dataset to: {output_dir} ...")

        with open(imu_csv_path, "w") as f_imu, open(gt_csv_path, "w") as f_gt:
            f_imu.write("frame_id,timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")
            f_gt.write("frame_id,timestamp,pos_x,pos_y,pos_z,roll,pitch,yaw,vel_x,vel_y,vel_z\n")

            frame_idx = 1
            for sensor_type, packet in self.stream_dataset():
                ts = packet["timestamp"]
                gt = packet["ground_truth"]
                fid = packet.get("frame_id", frame_idx)

                p = gt["position"]
                e = gt["orientation_euler"]
                v = gt["velocity"]

                if sensor_type == "camera":
                    frame_path = os.path.join(img_dir, f"frame_{frame_idx:06d}.png")
                    cv2.imwrite(frame_path, packet["frame"])

                    telemetry_json_records.append({
                        "frame_id": frame_idx,
                        "timestamp": round(ts, 4),
                        "position": {"x": round(float(p[0]), 4), "y": round(float(p[1]), 4), "z": round(float(p[2]), 4)},
                        "orientation": {"roll": round(float(e[0]), 4), "pitch": round(float(e[1]), 4), "yaw": round(float(e[2]), 4)},
                        "velocity": {"x": round(float(v[0]), 4), "y": round(float(v[1]), 4), "z": round(float(v[2]), 4)}
                    })
                    f_gt.write(f"{frame_idx},{ts:.6f},{p[0]:.4f},{p[1]:.4f},{p[2]:.4f},{e[0]:.4f},{e[1]:.4f},{e[2]:.4f},{v[0]:.4f},{v[1]:.4f},{v[2]:.4f}\n")
                    frame_idx += 1

                elif sensor_type == "imu":
                    a = packet["accel"]
                    g = packet["gyro"]
                    imu_json_records.append({
                        "frame_id": fid,
                        "timestamp": round(ts, 4),
                        "accelerometer": {"x": round(float(a[0]), 4), "y": round(float(a[1]), 4), "z": round(float(a[2]), 4)},
                        "gyroscope": {"x": round(float(g[0]), 4), "y": round(float(g[1]), 4), "z": round(float(g[2]), 4)}
                    })
                    f_imu.write(f"{fid},{ts:.6f},{a[0]:.5f},{a[1]:.5f},{a[2]:.5f},{g[0]:.5f},{g[1]:.5f},{g[2]:.5f}\n")

        with open(imu_json_path, "w") as f:
            json.dump(imu_json_records, f, indent=2)
        with open(telemetry_json_path, "w") as f:
            json.dump(telemetry_json_records, f, indent=2)

        print(f"[MockDataGenerator] Successfully exported {frame_idx - 1} 1280x720 frames, imu.json, and telemetry.json.")


if __name__ == "__main__":
    print("=== Testing MockDataGenerator (1280x720 HD) ===")
    generator = MockDataGenerator(trajectory_type="figure_eight", duration=1.0, imu_hz=100, camera_hz=30)

    imu_count = 0
    cam_count = 0
    sample_frame = None

    for sensor_type, packet in generator.stream_dataset():
        if sensor_type == "imu":
            imu_count += 1
        elif sensor_type == "camera":
            cam_count += 1
            if sample_frame is None:
                sample_frame = packet["frame"]

    print(f"Generated {imu_count} IMU packets and {cam_count} 720p Camera frames.")
    assert sample_frame.shape == (720, 1280, 3), f"Expected (720, 1280, 3), got {sample_frame.shape}"

    orb = cv2.ORB_create(nfeatures=2000)
    gray = cv2.cvtColor(sample_frame, cv2.COLOR_BGR2GRAY)
    keypoints, _ = orb.detectAndCompute(gray, None)
    print(f"ORB Detected {len(keypoints)} keypoints on 1280x720 HD frame.")
    assert len(keypoints) > 200, "Expected > 200 keypoints"
    print("MockDataGenerator update PASSED successfully!")
