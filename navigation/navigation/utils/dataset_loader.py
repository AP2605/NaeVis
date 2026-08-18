"""
Dataset Loader for Navigation & Localization Benchmarks (P3 Module).
====================================================================
Provides adapters and stream generators for real-world and synthetic flight datasets:
  1. Blender Simulation Dataset (images/frame_000001.png, imu.json, telemetry.json).
  2. EuRoC MAV Dataset (ASL format: mav0/cam0, mav0/imu0, mav0/state_groundtruth_estimate0).
  3. Generic CSV Flight Dataset (imu.csv, ground_truth.csv).

Yields chronologically synchronized sensor packets:
  - ('imu', {timestamp, frame_id, accel: [ax, ay, az], gyro: [gx, gy, gz], ground_truth})
  - ('camera', {timestamp, frame_id, frame: np.ndarray, image_path, ground_truth})
"""

import os
import csv
import json
import bisect
from typing import Dict, Any, Generator, Tuple, List, Optional
import numpy as np
import cv2


class BlenderDatasetLoader:
    """
    Parser for Blender Simulation datasets exported by P2 (Simulation Engineer).
    Expects:
      - images/frame_000001.png, frame_000002.png, ... (1280x720 RGB PNGs)
      - imu.json or imu.csv
      - telemetry.json or ground_truth.csv
    """

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.img_dir = os.path.join(dataset_dir, "images")
        self.imu_json_path = os.path.join(dataset_dir, "imu.json")
        self.telemetry_json_path = os.path.join(dataset_dir, "telemetry.json")
        self.imu_csv_path = os.path.join(dataset_dir, "imu.csv")
        self.gt_csv_path = os.path.join(dataset_dir, "ground_truth.csv")

        self.cam_records: List[Tuple[float, int, str]] = []  # (timestamp, frame_id, filepath)
        self.imu_records: List[Dict[str, Any]] = []
        self.gt_records: Dict[int, Dict[str, Any]] = {}       # keyed by frame_id

        self._load_dataset()

    def _load_dataset(self):
        # 1. Load Ground Truth / Telemetry
        if os.path.exists(self.telemetry_json_path):
            with open(self.telemetry_json_path, "r") as f:
                data = json.load(f)
                for item in data:
                    fid = item.get("frame_id", 0)
                    pos = item.get("position", {})
                    ori = item.get("orientation", {})
                    vel = item.get("velocity", {})

                    pos_arr = np.array([pos.get("x", 0.0), pos.get("y", 0.0), pos.get("z", 0.0)] if isinstance(pos, dict) else pos, dtype=np.float64)
                    ori_arr = np.array([ori.get("roll", 0.0), ori.get("pitch", 0.0), ori.get("yaw", 0.0)] if isinstance(ori, dict) else ori, dtype=np.float64)
                    vel_arr = np.array([vel.get("x", 0.0), vel.get("y", 0.0), vel.get("z", 0.0)] if isinstance(vel, dict) else vel, dtype=np.float64)

                    self.gt_records[fid] = {
                        "frame_id": fid,
                        "timestamp": float(item.get("timestamp", 0.0)),
                        "position": pos_arr,
                        "orientation_euler": ori_arr,
                        "velocity": vel_arr
                    }

        # 2. Load IMU data
        if os.path.exists(self.imu_json_path):
            with open(self.imu_json_path, "r") as f:
                data = json.load(f)
                for item in data:
                    fid = item.get("frame_id", 0)
                    acc = item.get("accelerometer", item.get("acceleration", {}))
                    gyr = item.get("gyroscope", {})

                    acc_arr = np.array([acc.get("x", 0.0), acc.get("y", 0.0), acc.get("z", 0.0)] if isinstance(acc, dict) else acc, dtype=np.float64)
                    gyr_arr = np.array([gyr.get("x", 0.0), gyr.get("y", 0.0), gyr.get("z", 0.0)] if isinstance(gyr, dict) else gyr, dtype=np.float64)

                    self.imu_records.append({
                        "frame_id": fid,
                        "timestamp": float(item.get("timestamp", 0.0)),
                        "accel": acc_arr,
                        "gyro": gyr_arr,
                        "ground_truth": self.gt_records.get(fid)
                    })
        elif os.path.exists(self.imu_csv_path):
            with open(self.imu_csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fid = int(row.get("frame_id", 0))
                    ts = float(row.get("timestamp", 0.0))
                    acc = np.array([float(row["acc_x"]), float(row["acc_y"]), float(row["acc_z"])])
                    gyr = np.array([float(row["gyro_x"]), float(row["gyro_y"]), float(row["gyro_z"])])
                    self.imu_records.append({
                        "frame_id": fid,
                        "timestamp": ts,
                        "accel": acc,
                        "gyro": gyr,
                        "ground_truth": self.gt_records.get(fid)
                    })

        # 3. Load Camera images (1280x720 PNG)
        if os.path.isdir(self.img_dir):
            files = sorted([f for f in os.listdir(self.img_dir) if f.endswith(".png") or f.endswith(".jpg")])
            cam_dt = 1.0 / 30.0
            for idx, fname in enumerate(files):
                fid = idx + 1
                ts = idx * cam_dt
                if fid in self.gt_records:
                    ts = self.gt_records[fid]["timestamp"]
                self.cam_records.append((ts, fid, os.path.join(self.img_dir, fname)))

    def stream_dataset(self) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        imu_idx = 0
        cam_idx = 0
        num_imu = len(self.imu_records)
        num_cam = len(self.cam_records)

        while imu_idx < num_imu or cam_idx < num_cam:
            imu_time = self.imu_records[imu_idx]["timestamp"] if imu_idx < num_imu else float("inf")
            cam_time = self.cam_records[cam_idx][0] if cam_idx < num_cam else float("inf")

            if imu_time <= cam_time:
                yield ("imu", self.imu_records[imu_idx])
                imu_idx += 1
            else:
                t, fid, img_path = self.cam_records[cam_idx]
                frame = cv2.imread(img_path) if os.path.exists(img_path) else None
                packet = {
                    "frame_id": fid,
                    "timestamp": t,
                    "frame": frame,
                    "image_path": img_path,
                    "ground_truth": self.gt_records.get(fid)
                }
                yield ("camera", packet)
                cam_idx += 1


class EuRoCDatasetLoader:
    """
    Parser for EuRoC MAV datasets (e.g., MH_01_easy, V1_01_easy).
    """

    def __init__(self, dataset_path: str, cam_name: str = "cam0", imu_name: str = "imu0"):
        self.dataset_path = dataset_path
        self.mav0_path = os.path.join(dataset_path, "mav0") if os.path.isdir(os.path.join(dataset_path, "mav0")) else dataset_path

        self.cam_dir = os.path.join(self.mav0_path, cam_name)
        self.imu_dir = os.path.join(self.mav0_path, imu_name)
        self.gt_dir = os.path.join(self.mav0_path, "state_groundtruth_estimate0")

        self.cam_records: List[Tuple[float, str]] = []
        self.imu_records: List[Tuple[float, np.ndarray, np.ndarray]] = []
        self.gt_records: List[Dict[str, Any]] = []
        self.gt_timestamps: List[float] = []

        self._load_records()

    def _load_records(self):
        imu_csv = os.path.join(self.imu_dir, "data.csv")
        if os.path.exists(imu_csv):
            with open(imu_csv, "r") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or row[0].startswith("#"):
                        continue
                    t_sec = float(row[0]) * 1e-9
                    gyro = np.array([float(row[1]), float(row[2]), float(row[3])], dtype=np.float64)
                    accel = np.array([float(row[4]), float(row[5]), float(row[6])], dtype=np.float64)
                    self.imu_records.append((t_sec, gyro, accel))

        cam_csv = os.path.join(self.cam_dir, "data.csv")
        cam_img_dir = os.path.join(self.cam_dir, "data")
        if os.path.exists(cam_csv):
            with open(cam_csv, "r") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or row[0].startswith("#"):
                        continue
                    t_sec = float(row[0]) * 1e-9
                    img_path = os.path.join(cam_img_dir, row[1].strip())
                    self.cam_records.append((t_sec, img_path))

        gt_csv = os.path.join(self.gt_dir, "data.csv")
        if os.path.exists(gt_csv):
            with open(gt_csv, "r") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or row[0].startswith("#"):
                        continue
                    t_sec = float(row[0]) * 1e-9
                    pos = np.array([float(row[1]), float(row[2]), float(row[3])], dtype=np.float64)
                    quat = np.array([float(row[4]), float(row[5]), float(row[6]), float(row[7])], dtype=np.float64)
                    vel = np.array([float(row[8]), float(row[9]), float(row[10])], dtype=np.float64)
                    self.gt_timestamps.append(t_sec)
                    self.gt_records.append({
                        "timestamp": t_sec,
                        "position": pos,
                        "orientation_quat": quat,
                        "velocity": vel
                    })

    def get_ground_truth_at(self, t_sec: float) -> Optional[Dict[str, Any]]:
        if not self.gt_timestamps:
            return None

        idx = bisect.bisect_left(self.gt_timestamps, t_sec)
        if idx == 0:
            return self.gt_records[0]
        if idx >= len(self.gt_timestamps):
            return self.gt_records[-1]

        t_prev = self.gt_timestamps[idx - 1]
        t_next = self.gt_timestamps[idx]
        return self.gt_records[idx - 1] if abs(t_sec - t_prev) < abs(t_sec - t_next) else self.gt_records[idx]

    def stream_dataset(self) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        imu_idx = 0
        cam_idx = 0
        num_imu = len(self.imu_records)
        num_cam = len(self.cam_records)

        t_start = min(
            self.imu_records[0][0] if num_imu > 0 else float("inf"),
            self.cam_records[0][0] if num_cam > 0 else float("inf")
        )

        while imu_idx < num_imu or cam_idx < num_cam:
            imu_time = self.imu_records[imu_idx][0] if imu_idx < num_imu else float("inf")
            cam_time = self.cam_records[cam_idx][0] if cam_idx < num_cam else float("inf")

            if imu_time <= cam_time:
                raw_t, gyro, accel = self.imu_records[imu_idx]
                gt = self.get_ground_truth_at(raw_t)
                packet = {
                    "timestamp": raw_t - t_start,
                    "raw_timestamp": raw_t,
                    "accel": accel,
                    "gyro": gyro,
                    "ground_truth": gt
                }
                yield ("imu", packet)
                imu_idx += 1
            else:
                raw_t, img_path = self.cam_records[cam_idx]
                frame = cv2.imread(img_path) if os.path.exists(img_path) else None
                gt = self.get_ground_truth_at(raw_t)
                packet = {
                    "timestamp": raw_t - t_start,
                    "raw_timestamp": raw_t,
                    "frame": frame,
                    "image_path": img_path,
                    "ground_truth": gt
                }
                yield ("camera", packet)
                cam_idx += 1


class GenericDatasetLoader:
    """
    Parser for datasets in CSV format.
    """

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.imu_csv = os.path.join(dataset_dir, "imu.csv")
        self.gt_csv = os.path.join(dataset_dir, "ground_truth.csv")
        self.img_dir = os.path.join(dataset_dir, "images")

        self.imu_records: List[Dict[str, Any]] = []
        self.gt_records: Dict[float, Dict[str, Any]] = {}
        self.cam_records: List[Tuple[float, str]] = []

        self._load_data()

    def _load_data(self):
        if os.path.exists(self.gt_csv):
            with open(self.gt_csv, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    t = float(row["timestamp"])
                    self.gt_records[round(t, 4)] = {
                        "timestamp": t,
                        "position": np.array([float(row["pos_x"]), float(row["pos_y"]), float(row["pos_z"])]),
                        "velocity": np.array([float(row["vel_x"]), float(row["vel_y"]), float(row["vel_z"])])
                    }

        if os.path.exists(self.imu_csv):
            with open(self.imu_csv, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    t = float(row["timestamp"])
                    self.imu_records.append({
                        "timestamp": t,
                        "accel": np.array([float(row["acc_x"]), float(row["acc_y"]), float(row["acc_z"])]),
                        "gyro": np.array([float(row["gyro_x"]), float(row["gyro_y"]), float(row["gyro_z"])]),
                        "ground_truth": self.gt_records.get(round(t, 4))
                    })

        if os.path.isdir(self.img_dir):
            files = sorted([f for f in os.listdir(self.img_dir) if f.endswith(".png") or f.endswith(".jpg")])
            cam_dt = 1.0 / 30.0
            for idx, fname in enumerate(files):
                t = idx * cam_dt
                self.cam_records.append((t, os.path.join(self.img_dir, fname)))

    def stream_dataset(self) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        imu_idx = 0
        cam_idx = 0
        num_imu = len(self.imu_records)
        num_cam = len(self.cam_records)

        while imu_idx < num_imu or cam_idx < num_cam:
            imu_time = self.imu_records[imu_idx]["timestamp"] if imu_idx < num_imu else float("inf")
            cam_time = self.cam_records[cam_idx][0] if cam_idx < num_cam else float("inf")

            if imu_time <= cam_time:
                yield ("imu", self.imu_records[imu_idx])
                imu_idx += 1
            else:
                t, img_path = self.cam_records[cam_idx]
                frame = cv2.imread(img_path) if os.path.exists(img_path) else None
                packet = {
                    "timestamp": t,
                    "frame": frame,
                    "image_path": img_path,
                    "ground_truth": self.gt_records.get(round(t, 4))
                }
                yield ("camera", packet)
                cam_idx += 1


if __name__ == "__main__":
    import shutil
    import tempfile
    from navigation.utils.mock_generator import MockDataGenerator

    print("=== Testing dataset_loader with BlenderDatasetLoader ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"1. Generating 1280x720 Blender synthetic dataset in temp folder: {tmp_dir}")
        generator = MockDataGenerator(trajectory_type="circular", duration=1.0, imu_hz=100, camera_hz=30)
        generator.export_dataset_to_disk(tmp_dir)

        print("2. Parsing Blender dataset via BlenderDatasetLoader...")
        loader = BlenderDatasetLoader(tmp_dir)

        imu_count = 0
        cam_count = 0
        sample_frame = None

        for sensor_type, packet in loader.stream_dataset():
            if sensor_type == "imu":
                imu_count += 1
                assert "accel" in packet and "gyro" in packet
                assert "frame_id" in packet
            elif sensor_type == "camera":
                cam_count += 1
                if sample_frame is None:
                    sample_frame = packet["frame"]
                assert "frame" in packet
                assert "frame_id" in packet

        print(f"Successfully streamed {imu_count} IMU packets and {cam_count} 720p Camera frames.")
        assert sample_frame.shape == (720, 1280, 3), f"Expected 720x1280, got {sample_frame.shape}"
        assert imu_count > 90, "Expected ~100 IMU packets"
        assert cam_count >= 29, "Expected ~30 Camera frames"

    print("All BlenderDatasetLoader tests PASSED successfully!")
