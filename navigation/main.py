"""
Navis Navigation & Localization Engine — Master CLI Entry Point (P3 Module).
===========================================================================
Unified standalone executable that runs the complete GPS-denied navigation pipeline:
  - Ingests Blender simulation datasets (or runs real-time synthetic flight generator).
  - Processes 1280x720 HD frames & 100 Hz IMU through INS + VO + 15-State EKF + Visual SLAM.
  - Computes quantitative ATE / RPE benchmark accuracy against ground truth.
  - Renders and exports high-resolution 2D and 3D trajectory plots to navigation/outputs/.
  - Exports standardized estimated telemetry JSON for P4 Dashboard integration.

Usage:
  python main.py --mock figure_eight --duration 5.0 --eval --plot
  python main.py --dataset ./my_flight_data --eval --plot --output ./navigation/outputs
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Any
import numpy as np

# Ensure workspace root is on sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from navigation.engine import NavigationEngine
from navigation.utils.dataset_loader import BlenderDatasetLoader
from navigation.utils.mock_generator import MockDataGenerator
from navigation.evaluation.metrics import TrajectoryEvaluator
from navigation.evaluation.plot_trajectory import TrajectoryPlotter


def run_navigation(
    dataset_path: str = None,
    mock_trajectory: str = "figure_eight",
    duration: float = 5.0,
    camera_hz: int = 30,
    imu_hz: int = 100,
    do_eval: bool = True,
    do_plot: bool = True,
    output_dir: str = "./navigation/outputs"
) -> Dict[str, Any]:
    """
    Executes the complete GPS-denied navigation state estimation pipeline.
    """
    os.makedirs(output_dir, exist_ok=True)
    print("\n" + "=" * 65)
    print("      NAVIS AUTONOMOUS GPS-DENIED NAVIGATION ENGINE (P3)      ")
    print("=" * 65)

    # 1. Prepare Data Stream
    if dataset_path and os.path.exists(dataset_path):
        print(f"[Engine] Loading dataset from: {os.path.abspath(dataset_path)}")
        loader = BlenderDatasetLoader(dataset_path)
        stream_generator = loader.stream_data()
        has_ground_truth = len(loader.ground_truth) > 0
    else:
        print(f"[Engine] Generating synthetic '{mock_trajectory}' flight stream ({duration}s @ {camera_hz} FPS)...")
        gen = MockDataGenerator(trajectory_type=mock_trajectory, duration=duration, imu_hz=imu_hz, camera_hz=camera_hz)
        stream_generator = gen.stream_dataset()
        has_ground_truth = True

    # 2. Initialize Navigation Engine
    engine = NavigationEngine()

    estimated_records: List[Dict[str, Any]] = []
    ground_truth_records: List[Dict[str, Any]] = []
    timestamps: List[float] = []

    frame_count = 0
    start_wall_time = time.time()
    latencies: List[float] = []

    print("\n[Engine] Starting real-time state estimation...")
    print("-" * 65)

    current_imu_accel = [0.0, 0.0, 9.81]
    current_imu_gyro = [0.0, 0.0, 0.0]

    for item in stream_generator:
        if isinstance(item, tuple):
            sensor_type, packet = item
        else:
            sensor_type = "camera" if "frame" in item or "image_path" in item else "imu"
            packet = item

        if sensor_type == "imu":
            acc = packet.get("accel", packet.get("accelerometer", [0.0, 0.0, 9.81]))
            gyr = packet.get("gyro", packet.get("gyroscope", [0.0, 0.0, 0.0]))
            if isinstance(acc, dict):
                current_imu_accel = [acc.get("x", 0.0), acc.get("y", 0.0), acc.get("z", 9.81)]
            else:
                current_imu_accel = list(acc)

            if isinstance(gyr, dict):
                current_imu_gyro = [gyr.get("x", 0.0), gyr.get("y", 0.0), gyr.get("z", 0.0)]
            else:
                current_imu_gyro = list(gyr)

        elif sensor_type == "camera":
            frame_count += 1
            ts = float(packet.get("timestamp", frame_count * (1.0 / camera_hz)))

            # Construct standardized SensorPacket matching info.md
            sensor_packet = {
                "frame_id": frame_count,
                "timestamp": ts,
                "camera": {
                    "frame": packet.get("frame"),
                    "image_path": packet.get("image_path"),
                    "width": 1280,
                    "height": 720
                },
                "imu": {
                    "acceleration": current_imu_accel,
                    "gyroscope": current_imu_gyro
                }
            }

            # Time the frame processing latency
            t0 = time.perf_counter()
            out_packet = engine.process_packet(sensor_packet)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(dt_ms)

            estimated_records.append(out_packet)
            timestamps.append(ts)

            if "ground_truth" in packet and packet["ground_truth"] is not None:
                gt = packet["ground_truth"]
                gt_pos = gt.get("position", [0.0, 0.0, 0.0])
                if isinstance(gt_pos, np.ndarray):
                    gt_pos = gt_pos.tolist()
                elif isinstance(gt_pos, dict):
                    gt_pos = [gt_pos.get("x", 0.0), gt_pos.get("y", 0.0), gt_pos.get("z", 0.0)]
                ground_truth_records.append(gt_pos)

            if frame_count % 15 == 0 or frame_count == 1:
                pose = out_packet["estimated_pose"]
                print(f" Frame #{frame_count:03d} | t={ts:.2f}s | Pose: ({pose['x']:.2f}, {pose['y']:.2f}, {pose['z']:.2f}) m | State: {out_packet['tracking_state']} | {dt_ms:.1f}ms")

    total_wall_time = time.time() - start_wall_time
    avg_fps = frame_count / max(total_wall_time, 1e-4)
    avg_latency = float(np.mean(latencies)) if latencies else 0.0

    print("-" * 65)
    print(f"[Engine] Finished processing {frame_count} frames in {total_wall_time:.2f}s ({avg_fps:.1f} FPS, {avg_latency:.2f}ms/frame).")

    # 3. Export Telemetry JSON & CSV for P4 Dashboard
    telemetry_json_path = os.path.join(output_dir, "estimated_telemetry.json")
    with open(telemetry_json_path, "w") as f:
        json.dump(estimated_records, f, indent=2)
    print(f"[Engine] Exported estimated telemetry JSON to: {telemetry_json_path}")

    # 4. Quantitative Evaluation (ATE & RPE)
    est_positions = np.array([
        [r["estimated_pose"]["x"], r["estimated_pose"]["y"], r["estimated_pose"]["z"]]
        for r in estimated_records
    ], dtype=np.float64)

    benchmark_report = {}
    if do_eval and len(ground_truth_records) >= 3:
        gt_positions = np.array(ground_truth_records, dtype=np.float64)
        benchmark_report = TrajectoryEvaluator.generate_full_report(
            est_positions, gt_positions, fps=avg_fps, latency_ms=avg_latency
        )
        TrajectoryEvaluator.print_benchmark_table(benchmark_report)

        report_json_path = os.path.join(output_dir, "benchmark_report.json")
        with open(report_json_path, "w") as f:
            json.dump(benchmark_report, f, indent=2)
        print(f"[Engine] Exported benchmark report JSON to: {report_json_path}")

    # 5. Render Trajectory Comparison Plots
    if do_plot and len(ground_truth_records) >= 3:
        gt_positions = np.array(ground_truth_records, dtype=np.float64)
        plotter = TrajectoryPlotter()

        p3d_path = os.path.join(output_dir, "trajectory_3d.png")
        p2d_path = os.path.join(output_dir, "trajectory_2d_topdown.png")
        perr_path = os.path.join(output_dir, "error_curves.png")

        plotter.plot_3d(est_positions, gt_positions, save_path=p3d_path)
        plotter.plot_2d_topdown(est_positions, gt_positions, save_path=p2d_path)
        plotter.plot_error_curves(np.array(timestamps), est_positions, gt_positions, save_path=perr_path)
        print(f"[Engine] All plots generated in: {os.path.abspath(output_dir)}")

    return {
        "frames_processed": frame_count,
        "avg_fps": avg_fps,
        "avg_latency_ms": avg_latency,
        "benchmark_report": benchmark_report
    }


def main():
    parser = argparse.ArgumentParser(description="Navis Autonomous Navigation (P3) Master Executable.")
    parser.add_argument("--dataset", type=str, default=None, help="Path to Blender dataset folder")
    parser.add_argument("--mock", type=str, default="figure_eight", choices=["figure_eight", "circular", "straight_line", "hover"], help="Synthetic trajectory type")
    parser.add_argument("--duration", type=float, default=4.0, help="Flight duration in seconds for mock mode")
    parser.add_argument("--eval", action="store_true", default=True, help="Compute ATE/RPE benchmark accuracy")
    parser.add_argument("--plot", action="store_true", default=True, help="Generate 2D and 3D trajectory plots")
    parser.add_argument("--output", type=str, default="./navigation/outputs", help="Output directory for results")

    args = parser.parse_args()

    run_navigation(
        dataset_path=args.dataset,
        mock_trajectory=args.mock,
        duration=args.duration,
        do_eval=args.eval,
        do_plot=args.plot,
        output_dir=args.output
    )


if __name__ == "__main__":
    main()
