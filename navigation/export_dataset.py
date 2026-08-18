"""
Flight Dataset Exporter Tool (P3 Module).
=========================================
Generates and exports realistic synthetic flight datasets formatted for
Blender simulation testing, P4 dashboard integration, and offline evaluation.

Usage:
  python export_dataset.py --trajectory figure_eight --duration 5.0 --output ./sample_dataset
  python export_dataset.py --trajectory circular --duration 10.0 --output ./circular_dataset
"""

import argparse
import os
import sys

# Ensure root workspace is in sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from navigation.utils.mock_generator import MockDataGenerator


def main():
    parser = argparse.ArgumentParser(description="Export synthetic drone flight datasets matching Blender simulation specs.")
    parser.add_argument(
        "--trajectory",
        type=str,
        default="figure_eight",
        choices=["figure_eight", "circular", "straight_line", "hover"],
        help="Type of 3D trajectory profile (default: figure_eight)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Flight duration in seconds (default: 5.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./flight_dataset",
        help="Output directory path (default: ./flight_dataset)"
    )
    parser.add_argument(
        "--imu-hz",
        type=int,
        default=100,
        help="IMU sampling rate in Hz (default: 100)"
    )
    parser.add_argument(
        "--camera-hz",
        type=int,
        default=30,
        help="Camera frame rate in FPS (default: 30)"
    )
    parser.add_argument(
        "--no-noise",
        action="store_true",
        help="Disable sensor noise for ideal ground truth testing"
    )

    args = parser.parse_args()

    print(f"\n[Exporter] Generating '{args.trajectory}' trajectory ({args.duration}s)...")
    print(f"[Exporter] IMU Rate: {args.imu_hz} Hz | Camera Rate: {args.camera_hz} FPS | Resolution: 1280x720 HD")

    generator = MockDataGenerator(
        trajectory_type=args.trajectory,
        duration=args.duration,
        imu_hz=args.imu_hz,
        camera_hz=args.camera_hz,
        add_sensor_noise=not args.no_noise
    )

    generator.export_dataset_to_disk(args.output)
    print(f"\n[Exporter] Finished! Dataset exported to: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
