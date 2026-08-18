"""
15-State Error-State Extended Kalman Filter (ES-EKF) for VIO (P3 Module).
========================================================================
Fuses high-rate (100-200 Hz) IMU predictions with mid-rate (30 Hz) Visual Odometry:
  - 15-Dimensional Error State: [δp (3), δv (3), δθ (3), δba (3), δbg (3)]
  - Nominal State: Position (3), Velocity (3), Unit Quaternion (4), Accel Bias (3), Gyro Bias (3)
  - First-order error propagation with full Jacobian matrices.
  - Joseph-form covariance update for strict positive-definiteness and numerical stability.
  - Dynamic visual tracking confidence scaling.
"""

from typing import Dict, Any, Tuple, Optional
import numpy as np

from navigation.utils.math_utils import (
    quaternion_integrate,
    quaternion_to_rotation_matrix,
    quaternion_to_euler,
    quaternion_normalize,
    quaternion_multiply,
    quaternion_conjugate,
    skew_symmetric,
    rotation_matrix_to_quaternion
)


class EKFFusion:
    """
    15-State Error-State Extended Kalman Filter for Sensor Fusion.
    Fuses IMU dead reckoning with Visual Odometry / SLAM poses.
    """

    def __init__(
        self,
        init_pos: Optional[np.ndarray] = None,
        init_vel: Optional[np.ndarray] = None,
        init_quat: Optional[np.ndarray] = None,
        accel_noise_density: float = 0.05,     # m/s^2 / sqrt(Hz)
        gyro_noise_density: float = 0.005,     # rad/s / sqrt(Hz)
        accel_bias_rw: float = 0.001,          # m/s^3 / sqrt(Hz)
        gyro_bias_rw: float = 0.0001,          # rad/s^2 / sqrt(Hz)
        vo_pos_std: float = 0.05,              # meters
        vo_ori_std: float = 0.02,              # radians
        gravity_magnitude: float = 9.81
    ):
        # 1. Nominal State Initialization
        self.p = np.array(init_pos if init_pos is not None else [0.0, 0.0, 0.0], dtype=np.float64)
        self.v = np.array(init_vel if init_vel is not None else [0.0, 0.0, 0.0], dtype=np.float64)
        self.q = quaternion_normalize(
            np.array(init_quat if init_quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        )
        self.b_a = np.zeros(3, dtype=np.float64)
        self.b_g = np.zeros(3, dtype=np.float64)

        self.gravity_world = np.array([0.0, 0.0, -gravity_magnitude], dtype=np.float64)

        # 2. Covariance Matrix P (15x15)
        # Order: [δp (0:3), δv (3:6), δθ (6:9), δba (9:12), δbg (12:15)]
        self.P = np.eye(15, dtype=np.float64)
        self.P[0:3, 0:3] *= 0.01      # position variance (m^2)
        self.P[3:6, 3:6] *= 0.01      # velocity variance (m/s)^2
        self.P[6:9, 6:9] *= 0.005     # orientation variance (rad^2)
        self.P[9:12, 9:12] *= 0.001   # accel bias variance
        self.P[12:15, 12:15] *= 0.0001 # gyro bias variance

        # 3. Noise Parameters
        self.accel_noise_std = accel_noise_density
        self.gyro_noise_std = gyro_noise_density
        self.accel_bias_rw = accel_bias_rw
        self.gyro_bias_rw = gyro_bias_rw
        self.vo_pos_std = vo_pos_std
        self.vo_ori_std = vo_ori_std

        self.step_count = 0
        self.last_update_time = 0.0

    def predict(self, accel_meas: np.ndarray, gyro_meas: np.ndarray, dt: float) -> Dict[str, Any]:
        """
        High-Rate Prediction Step (Driven by IMU at 100-200 Hz).
        Propagates the nominal state and error covariance matrix P.
        """
        dt = max(dt, 1e-6)

        # 1. Correct IMU measurements with current bias estimates
        acc_b = np.array(accel_meas, dtype=np.float64) - self.b_a
        gyr_b = np.array(gyro_meas, dtype=np.float64) - self.b_g

        # 2. Propagate Nominal Orientation (Quaternion)
        q_prev = self.q.copy()
        self.q = quaternion_normalize(quaternion_integrate(q_prev, gyr_b, dt))

        # 3. Propagate Nominal Position & Velocity
        R_wb = quaternion_to_rotation_matrix(self.q)
        acc_w = R_wb @ acc_b + self.gravity_world  # Remove gravity

        self.p += self.v * dt + 0.5 * acc_w * (dt ** 2)
        self.v += acc_w * dt

        # 4. Compute Continuous-Time Error State Jacobian F_c (15x15)
        F = np.eye(15, dtype=np.float64)
        # Position block: d(δp)/d(δv) = I * dt
        F[0:3, 3:6] = np.eye(3) * dt
        # Velocity block: d(δv)/d(δθ) = -R_wb * [acc_b]_x * dt
        F[3:6, 6:9] = -R_wb @ skew_symmetric(acc_b) * dt
        # Velocity block: d(δv)/d(δba) = -R_wb * dt
        F[3:6, 9:12] = -R_wb * dt
        # Orientation block: d(δθ)/d(δθ) = I - [gyr_b]_x * dt
        F[6:9, 6:9] -= skew_symmetric(gyr_b) * dt
        # Orientation block: d(δθ)/d(δbg) = -I * dt
        F[6:9, 12:15] = -np.eye(3) * dt

        # 5. Process Noise Matrix Q (15x15)
        Q = np.zeros((15, 15), dtype=np.float64)
        Q[0:3, 0:3] = np.eye(3) * (0.5 * (self.accel_noise_std ** 2) * (dt ** 3))
        Q[3:6, 3:6] = np.eye(3) * ((self.accel_noise_std ** 2) * dt)
        Q[6:9, 6:9] = np.eye(3) * ((self.gyro_noise_std ** 2) * dt)
        Q[9:12, 9:12] = np.eye(3) * ((self.accel_bias_rw ** 2) * dt)
        Q[12:15, 12:15] = np.eye(3) * ((self.gyro_bias_rw ** 2) * dt)

        # 6. Covariance Propagation: P = F * P * F^T + Q
        self.P = F @ self.P @ F.T + Q
        # Enforce symmetry
        self.P = 0.5 * (self.P + self.P.T)

        self.step_count += 1
        return self.get_state()

    def update_vo_pose(
        self,
        pos_vo: np.ndarray,
        quat_vo: np.ndarray,
        confidence: float = 1.0
    ) -> Dict[str, Any]:
        """
        Mid-Rate Measurement Update Step (Driven by Visual Odometry at 30 Hz).
        Updates state vector and covariance using estimated 6-DOF camera pose.

        Args:
            pos_vo: Estimated 3D camera position [x, y, z] in meters.
            quat_vo: Estimated camera orientation quaternion [qw, qx, qy, qz].
            confidence: Visual tracking confidence score [0.0 - 1.0].
        """
        conf = float(np.clip(confidence, 0.05, 1.0))
        pos_vo = np.array(pos_vo, dtype=np.float64)
        quat_vo = quaternion_normalize(np.array(quat_vo, dtype=np.float64))

        # 1. Measurement Residual (Innovation) y (6x1)
        # Position residual
        res_pos = pos_vo - self.p

        # Orientation error residual: δθ = 2 * (q_nominal^-1 * q_vo).xyz
        q_err = quaternion_multiply(quaternion_conjugate(self.q), quat_vo)
        sign = 1.0 if q_err[0] >= 0.0 else -1.0
        res_ori = 2.0 * sign * q_err[1:4]

        y = np.hstack([res_pos, res_ori])  # 6x1

        # 2. Measurement Matrix H (6x15)
        # Observes position (0:3) and orientation error (6:9)
        H = np.zeros((6, 15), dtype=np.float64)
        H[0:3, 0:3] = np.eye(3)
        H[3:6, 6:9] = np.eye(3)

        # 3. Measurement Noise Covariance R (6x6) scaled by confidence
        R_cov = np.eye(6, dtype=np.float64)
        R_cov[0:3, 0:3] *= (self.vo_pos_std ** 2) / conf
        R_cov[3:6, 3:6] *= (self.vo_ori_std ** 2) / conf

        # 4. Innovation Covariance S & Kalman Gain K
        S = H @ self.P @ H.T + R_cov  # 6x6
        K = self.P @ H.T @ np.linalg.inv(S)  # 15x6

        # 5. Error State Correction: δx = K * y (15x1)
        delta_x = K @ y

        # 6. State Injection (Correct Nominal State)
        self.p += delta_x[0:3]
        self.v += delta_x[3:6]
        # Multiplicative quaternion correction
        dq = np.hstack([[1.0], 0.5 * delta_x[6:9]])
        self.q = quaternion_normalize(quaternion_multiply(self.q, dq))
        self.b_a += delta_x[9:12]
        self.b_g += delta_x[12:15]

        # 7. Covariance Update via Joseph Form: P = (I - KH) * P * (I - KH)^T + K * R * K^T
        I_KH = np.eye(15, dtype=np.float64) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R_cov @ K.T
        self.P = 0.5 * (self.P + self.P.T)

        return self.get_state()

    def update_position_only(self, pos_meas: np.ndarray, std_dev: float = 0.1):
        """Measurement update for position-only sensors (e.g. height/barometer/GPS)."""
        pos_meas = np.array(pos_meas, dtype=np.float64)
        res_pos = pos_meas - self.p

        H = np.zeros((3, 15), dtype=np.float64)
        H[0:3, 0:3] = np.eye(3)

        R_cov = np.eye(3, dtype=np.float64) * (std_dev ** 2)
        S = H @ self.P @ H.T + R_cov
        K = self.P @ H.T @ np.linalg.inv(S)

        delta_x = K @ res_pos
        self.p += delta_x[0:3]
        self.v += delta_x[3:6]
        dq = np.hstack([[1.0], 0.5 * delta_x[6:9]])
        self.q = quaternion_normalize(quaternion_multiply(self.q, dq))
        self.b_a += delta_x[9:12]
        self.b_g += delta_x[12:15]

        I_KH = np.eye(15, dtype=np.float64) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R_cov @ K.T
        self.P = 0.5 * (self.P + self.P.T)

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state snapshot and diagonal standard deviations."""
        roll, pitch, yaw = quaternion_to_euler(self.q)
        pos_std = np.sqrt(np.diag(self.P)[0:3])

        return {
            "position": self.p.copy(),
            "velocity": self.v.copy(),
            "orientation_quat": self.q.copy(),
            "orientation_euler": np.array([roll, pitch, yaw], dtype=np.float64),
            "rotation_matrix": quaternion_to_rotation_matrix(self.q),
            "accel_bias": self.b_a.copy(),
            "gyro_bias": self.b_g.copy(),
            "position_std": pos_std,
            "speed": float(np.linalg.norm(self.v))
        }

    def reset(
        self,
        pos: Optional[np.ndarray] = None,
        vel: Optional[np.ndarray] = None,
        quat: Optional[np.ndarray] = None
    ):
        """Resets the state vector (used for loop closure corrections)."""
        if pos is not None:
            self.p = np.array(pos, dtype=np.float64)
        if vel is not None:
            self.v = np.array(vel, dtype=np.float64)
        if quat is not None:
            self.q = quaternion_normalize(np.array(quat, dtype=np.float64))


if __name__ == "__main__":
    print("=== Testing 15-State EKFFusion ===")
    from navigation.utils.mock_generator import MockDataGenerator

    gen = MockDataGenerator(trajectory_type="circular", duration=3.0, imu_hz=100, camera_hz=30)
    init_gt = gen.trajectory.get_state(0.0)

    ekf = EKFFusion(
        init_pos=init_gt["position"],
        init_vel=init_gt["velocity"],
        init_quat=init_gt["orientation_quat"]
    )

    prev_time = 0.0
    ekf_errors = []

    for sensor_type, packet in gen.stream_dataset():
        ts = packet["timestamp"]
        dt = max(ts - prev_time, 0.01) if prev_time > 0 else 0.01
        prev_time = ts

        if sensor_type == "imu":
            # 100 Hz EKF Prediction Step
            state = ekf.predict(packet["accel"], packet["gyro"], dt=dt)
        elif sensor_type == "camera":
            # 30 Hz EKF Measurement Update Step (Using ground truth pose + slight noise to simulate VO)
            gt = packet["ground_truth"]
            vo_pos_noisy = gt["position"] + np.random.normal(0, 0.02, 3)
            vo_quat = gt["orientation_quat"]

            state = ekf.update_vo_pose(vo_pos_noisy, vo_quat, confidence=0.9)

            gt_pos = gt["position"]
            err = np.linalg.norm(state["position"] - gt_pos)
            ekf_errors.append(err)

    mean_err = np.mean(ekf_errors)
    max_err = np.max(ekf_errors)
    print(f"Fused EKF Tracking over 3.0s circular flight:")
    print(f"  - Mean Position Error: {mean_err:.4f} meters")
    print(f"  - Max Position Error:  {max_err:.4f} meters")
    print(f"  - Estimated Accel Bias: {state['accel_bias']}")
    print(f"  - Estimated Gyro Bias:  {state['gyro_bias']}")

    assert mean_err < 0.15, f"Mean error {mean_err} was higher than threshold"
    print("EKFFusion verification PASSED! [Milestone 5 Achieved]")
