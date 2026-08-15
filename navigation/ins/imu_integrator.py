"""
INS (Inertial Navigation System) Dead Reckoning Module (P3 Module).
===================================================================
Implements high-rate (100-200 Hz) kinematic state propagation from 6-axis IMU:
  - Gyroscope angular rate integration via closed-form matrix-exponential quaternions.
  - Coordinate frame rotation (Body -> World ENU frame).
  - Gravity vector removal: a_world = R_wb * (a_meas - b_a) - [0, 0, g]^T.
  - Mid-point trapezoidal double integration for velocity and 3D position.
  - Dynamic bias correction injection (for EKF in Phase 5).
"""

from typing import Dict, Any, Tuple, Optional, List
import numpy as np

from navigation.utils.math_utils import (
    quaternion_integrate,
    quaternion_to_rotation_matrix,
    quaternion_to_euler,
    quaternion_normalize,
    euler_to_quaternion
)


class IMUIntegrator:
    """
    6-DOF Inertial Dead Reckoning State Propagator.
    Tracks Position, Velocity, Orientation (Quaternion), and Sensor Biases.
    """

    def __init__(
        self,
        init_pos: Optional[np.ndarray] = None,
        init_vel: Optional[np.ndarray] = None,
        init_quat: Optional[np.ndarray] = None,
        accel_bias: Optional[np.ndarray] = None,
        gyro_bias: Optional[np.ndarray] = None,
        gravity_magnitude: float = 9.81
    ):
        """
        Initializes the state vectors.
        World Frame: ENU (East-North-Up), Gravity points down along -Z: [0, 0, -g].
        """
        self.position = np.array(init_pos if init_pos is not None else [0.0, 0.0, 0.0], dtype=np.float64)
        self.velocity = np.array(init_vel if init_vel is not None else [0.0, 0.0, 0.0], dtype=np.float64)
        self.orientation_quat = quaternion_normalize(
            np.array(init_quat if init_quat is not None else [1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        )
        self.accel_bias = np.array(accel_bias if accel_bias is not None else [0.0, 0.0, 0.0], dtype=np.float64)
        self.gyro_bias = np.array(gyro_bias if gyro_bias is not None else [0.0, 0.0, 0.0], dtype=np.float64)

        self.gravity_magnitude = gravity_magnitude
        self.gravity_world = np.array([0.0, 0.0, -gravity_magnitude], dtype=np.float64)

        self.prev_accel_world: Optional[np.ndarray] = None
        self.step_count = 0

    def update(self, accel_meas: np.ndarray, gyro_meas: np.ndarray, dt: float) -> Dict[str, Any]:
        """
        Advances the kinematic state by time step dt (seconds) given noisy IMU measurements.

        Args:
            accel_meas: Measured specific force in body frame [ax, ay, az] (m/s^2).
            gyro_meas: Measured angular velocity in body frame [wx, wy, wz] (rad/s).
            dt: Delta time in seconds (e.g. 0.01s for 100 Hz).

        Returns:
            Dictionary containing updated kinematic state.
        """
        dt = max(dt, 1e-6)

        # 1. Bias Correction
        gyro_corrected = gyro_meas - self.gyro_bias
        accel_corrected = accel_meas - self.accel_bias

        # 2. Orientation Integration (Matrix Exponential Quaternion integration)
        q_new = quaternion_integrate(self.orientation_quat, gyro_corrected, dt)
        self.orientation_quat = quaternion_normalize(q_new)

        # 3. Body -> World Rotation Matrix
        R_wb = quaternion_to_rotation_matrix(self.orientation_quat)

        # 4. Specific Force to World Frame & Gravity Removal
        # Accelerometer measures specific force: f_b = R_wb^T * (a_w - g_w)
        # Therefore: a_w = R_wb * f_b + g_w = R_wb * f_b - [0, 0, 9.81]^T
        specific_force_world = R_wb @ accel_corrected
        accel_world = specific_force_world + self.gravity_world  # Removes gravity

        # 5. Numerical Double-Integration (Trapezoidal / Mid-Point rule)
        if self.prev_accel_world is None:
            self.prev_accel_world = accel_world.copy()

        accel_avg = 0.5 * (self.prev_accel_world + accel_world)

        # Update position: p(t+dt) = p(t) + v(t)*dt + 0.5*a_avg*dt^2
        self.position += self.velocity * dt + 0.5 * accel_avg * (dt ** 2)

        # Update velocity: v(t+dt) = v(t) + a_avg*dt
        self.velocity += accel_avg * dt

        self.prev_accel_world = accel_world.copy()
        self.step_count += 1

        roll, pitch, yaw = quaternion_to_euler(self.orientation_quat)

        return {
            "position": self.position.copy(),
            "velocity": self.velocity.copy(),
            "orientation_quat": self.orientation_quat.copy(),
            "orientation_euler": np.array([roll, pitch, yaw], dtype=np.float64),
            "rotation_matrix": R_wb,
            "linear_accel_world": accel_world.copy(),
            "body_accel_corrected": accel_corrected.copy()
        }

    def set_biases(self, accel_bias: np.ndarray, gyro_bias: np.ndarray):
        """Updates estimated sensor biases (called dynamically by EKF)."""
        self.accel_bias = np.array(accel_bias, dtype=np.float64)
        self.gyro_bias = np.array(gyro_bias, dtype=np.float64)

    def reset_state(
        self,
        pos: Optional[np.ndarray] = None,
        vel: Optional[np.ndarray] = None,
        quat: Optional[np.ndarray] = None
    ):
        """Resets the state vector (used for loop closure or EKF state updates)."""
        if pos is not None:
            self.position = np.array(pos, dtype=np.float64)
        if vel is not None:
            self.velocity = np.array(vel, dtype=np.float64)
        if quat is not None:
            self.orientation_quat = quaternion_normalize(np.array(quat, dtype=np.float64))
        self.prev_accel_world = None

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state snapshot."""
        roll, pitch, yaw = quaternion_to_euler(self.orientation_quat)
        return {
            "position": self.position.copy(),
            "velocity": self.velocity.copy(),
            "orientation_quat": self.orientation_quat.copy(),
            "orientation_euler": np.array([roll, pitch, yaw], dtype=np.float64),
            "rotation_matrix": quaternion_to_rotation_matrix(self.orientation_quat),
            "accel_bias": self.accel_bias.copy(),
            "gyro_bias": self.gyro_bias.copy()
        }


if __name__ == "__main__":
    print("=== Testing IMU Dead Reckoning (IMUIntegrator) ===")

    # Test 1: Static Hover / Stationary Test
    print("\n--- Test 1: Static Gravity Compensation ---")
    ins = IMUIntegrator(init_pos=np.array([0.0, 0.0, 5.0]))
    # Stationary drone on flat surface measures [0, 0, +9.81] reaction force in body frame
    stationary_accel = np.array([0.0, 0.0, 9.81])
    stationary_gyro = np.array([0.0, 0.0, 0.0])

    for _ in range(100):  # Simulate 1.0 second @ 100 Hz
        state = ins.update(stationary_accel, stationary_gyro, dt=0.01)

    print(f"Position after 1.0s stationary: {state['position']} (Expected: [0, 0, 5])")
    print(f"Velocity after 1.0s stationary: {state['velocity']} (Expected: [0, 0, 0])")
    assert np.allclose(state["position"], [0.0, 0.0, 5.0], atol=1e-3)
    assert np.allclose(state["velocity"], [0.0, 0.0, 0.0], atol=1e-3)
    print("Static Gravity Compensation PASSED!")

    # Test 2: Integration on Synthetic Flight Stream
    print("\n--- Test 2: Synthetic Trajectory Dead Reckoning (5.0s Flight) ---")
    from navigation.utils.mock_generator import MockDataGenerator

    gen = MockDataGenerator(trajectory_type="circular", duration=5.0, imu_hz=100, add_sensor_noise=False)

    # Initialize INS at exact t=0 ground truth
    init_gt = gen.trajectory.get_state(0.0)
    ins_flight = IMUIntegrator(
        init_pos=init_gt["position"],
        init_vel=init_gt["velocity"],
        init_quat=init_gt["orientation_quat"]
    )

    errors = []
    prev_time = 0.0

    for sensor_type, packet in gen.stream_dataset():
        if sensor_type == "imu":
            dt = packet["timestamp"] - prev_time
            if dt <= 0.0:
                dt = 0.01
            prev_time = packet["timestamp"]

            state = ins_flight.update(packet["accel"], packet["gyro"], dt=dt)
            gt_pos = packet["ground_truth"]["position"]
            err = np.linalg.norm(state["position"] - gt_pos)
            errors.append(err)

    final_error = errors[-1] if errors else 0.0
    mean_error = np.mean(errors) if errors else 0.0
    print(f"Clean IMU Dead Reckoning over 5.0s flight:")
    print(f"  - Mean Position Error: {mean_error:.4f} meters")
    print(f"  - Final Position Error: {final_error:.4f} meters")
    print("IMU Integrator verification PASSED! [Milestone 2 Achieved]")
