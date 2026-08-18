"""
Monocular Metric Scale Estimator Module (P3 Module).
====================================================
Solves the monocular scale ambiguity (converting unit translation vectors to meters)
by correlating visual displacement with high-rate IMU acceleration and velocity:
  - Sliding-window IMU double-integration for physical metric distance.
  - Motion gating (rejects noisy scale updates during zero-acceleration hover).
  - Exponential Moving Average (EMA) smoothing for stability.
  - Altitude/Barometric constraint fusion (when available).
"""

from collections import deque
from typing import Optional, Deque, Tuple
import numpy as np


class ScaleEstimator:
    """
    Estimates the physical metric scale factor s (meters per frame)
    such that: t_metric = s * t_unit.
    """

    def __init__(
        self,
        window_size: int = 10,
        default_scale: float = 0.067,   # ~2.0 m/s at 30 FPS nominal prior
        alpha: float = 0.15,            # EMA filter smoothing factor
        min_accel_threshold: float = 0.08, # m/s^2 motion gate
        min_scale_clamp: float = 0.002, # 2mm minimum displacement per frame
        max_scale_clamp: float = 1.5    # 1.5m maximum displacement per frame
    ):
        self.window_size = window_size
        self.current_scale = float(default_scale)
        self.alpha = float(alpha)
        self.min_accel_threshold = float(min_accel_threshold)
        self.min_scale_clamp = float(min_scale_clamp)
        self.max_scale_clamp = float(max_scale_clamp)

        # Buffers for sliding-window estimation
        # Stores (linear_accel_world, velocity_world, dt)
        self.imu_buffer: Deque[Tuple[np.ndarray, np.ndarray, float]] = deque(maxlen=window_size * 5)
        # Stores (vo_unit_t, dt)
        self.vo_buffer: Deque[Tuple[np.ndarray, float]] = deque(maxlen=window_size)

        self.update_count = 0

    def add_imu_sample(self, linear_accel_world: np.ndarray, velocity_world: np.ndarray, dt: float):
        """
        Adds high-rate IMU measurement to the sliding buffer.

        Args:
            linear_accel_world: Gravity-compensated acceleration in world frame (m/s^2).
            velocity_world: Integrated velocity in world frame (m/s).
            dt: Delta time of IMU sample (s).
        """
        self.imu_buffer.append((np.array(linear_accel_world, dtype=np.float64), np.array(velocity_world, dtype=np.float64), float(dt)))

    def estimate_scale(
        self,
        vo_unit_translation: np.ndarray,
        dt: float,
        altitude_change: Optional[float] = None
    ) -> float:
        """
        Calculates and returns the smoothed metric scale factor s (in meters).

        Args:
            vo_unit_translation: Unit translation vector from Visual Odometry (shape: 3,).
            dt: Delta time of camera frame (s).
            altitude_change: Optional vertical physical displacement (meters) from barometer/height sensor.

        Returns:
            Smoothed metric scale factor s in meters.
        """
        unit_t = np.array(vo_unit_translation, dtype=np.float64).flatten()
        unit_norm = np.linalg.norm(unit_t)

        if unit_norm < 1e-6:
            return self.current_scale

        self.vo_buffer.append((unit_t, float(dt)))
        self.update_count += 1

        scale_candidates = []

        # 1. Altitude / Barometric Constraint Fusion
        if altitude_change is not None and abs(unit_t[2]) > 0.15:
            s_alt = abs(float(altitude_change)) / abs(float(unit_t[2]))
            if self.min_scale_clamp <= s_alt <= self.max_scale_clamp:
                scale_candidates.append(s_alt)

        # 2. IMU-VO Sliding Window Correlation
        if len(self.imu_buffer) >= 5 and len(self.vo_buffer) >= 2:
            # Integrate IMU displacement over buffer
            total_imu_disp = np.zeros(3, dtype=np.float64)
            accel_mags = []

            for acc, vel, idt in self.imu_buffer:
                total_imu_disp += vel * idt + 0.5 * acc * (idt ** 2)
                accel_mags.append(np.linalg.norm(acc))

            avg_accel = np.mean(accel_mags) if accel_mags else 0.0
            dist_imu = float(np.linalg.norm(total_imu_disp))

            # Cumulative VO unit distance
            total_vo_unit = np.sum([vt for vt, _ in self.vo_buffer], axis=0)
            dist_vo = float(np.linalg.norm(total_vo_unit))

            # Motion Gate: only compute ratio if there is detectable acceleration/motion
            if avg_accel > self.min_accel_threshold and dist_vo > 1e-3 and dist_imu > 1e-3:
                s_imu = dist_imu / dist_vo
                if self.min_scale_clamp <= s_imu <= self.max_scale_clamp:
                    scale_candidates.append(s_imu)

        # 3. Apply Update via Exponential Moving Average (EMA)
        if scale_candidates:
            s_measured = float(np.median(scale_candidates))
            # Smoothly update scale
            self.current_scale = self.alpha * s_measured + (1.0 - self.alpha) * self.current_scale
            # Clamp to safe envelope
            self.current_scale = float(np.clip(self.current_scale, self.min_scale_clamp, self.max_scale_clamp))

        return self.current_scale

    def get_current_scale(self) -> float:
        """Returns the active metric scale."""
        return self.current_scale

    def reset(self, initial_scale: Optional[float] = None):
        """Resets the buffers and scale factor."""
        if initial_scale is not None:
            self.current_scale = float(initial_scale)
        self.imu_buffer.clear()
        self.vo_buffer.clear()
        self.update_count = 0


if __name__ == "__main__":
    print("=== Testing ScaleEstimator ===")
    estimator = ScaleEstimator(default_scale=0.05, alpha=0.2)

    # Simulate drone moving at constant 2.0 m/s with 30 FPS camera (expected ~0.067 m/frame)
    # Simulated IMU stream at 100 Hz with some acceleration
    v_sim = np.array([2.0, 0.0, 0.0])
    a_sim = np.array([0.2, 0.0, 0.0])  # 0.2 m/s^2 forward acceleration
    dt_imu = 0.01

    vo_unit_t = np.array([1.0, 0.0, 0.0])  # pure forward visual motion
    dt_cam = 1.0 / 30.0

    # Feed 1.0 second of data
    for step in range(30):
        # 3.33 IMU steps per camera frame
        for _ in range(3):
            estimator.add_imu_sample(a_sim, v_sim, dt_imu)

        scale = estimator.estimate_scale(vo_unit_t, dt_cam)

    print(f"Initial prior scale: 0.0500 m/frame")
    print(f"Recovered metric scale: {scale:.4f} m/frame (Expected: ~0.060-0.070 m/frame)")
    assert 0.04 <= scale <= 0.09, f"Scale {scale} outside expected range"
    print("ScaleEstimator verification PASSED! [Milestone 4 Achieved]")
