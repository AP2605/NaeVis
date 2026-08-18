"""
Math & Geometric Utilities for Navigation & State Estimation.
============================================================
Contains mathematical functions for 3D rotations, coordinate frame transforms,
quaternions, Euler angles, and kinematics used throughout INS, VO, EKF, and SLAM.

Quaternion Convention: Hamilton format [qw, qx, qy, qz] where qw is the real/scalar part.
"""

from typing import Tuple
import numpy as np


def quaternion_normalize(q: np.ndarray) -> np.ndarray:
    """Normalizes a quaternion [qw, qx, qy, qz] to unit length."""
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    return q / norm


def quaternion_conjugate(q: np.ndarray) -> np.ndarray:
    """Returns the conjugate / inverse of unit quaternion [qw, -qx, -qy, -qz]."""
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=np.float64)


def quaternion_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """
    Computes Hamilton product of two quaternions q = q1 * q2.
    Format: [qw, qx, qy, qz]
    """
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2

    qw = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    qx = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    qy = w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2
    qz = w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2

    return quaternion_normalize(np.array([qw, qx, qy, qz], dtype=np.float64))


def quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """
    Converts unit quaternion [qw, qx, qy, qz] to 3x3 rotation matrix R.
    R rotates vectors from body frame to world frame: v_w = R * v_b.
    """
    q_norm = quaternion_normalize(q)
    w, x, y, z = q_norm

    R = np.array([
        [1.0 - 2.0 * (y**2 + z**2), 2.0 * (x * y - w * z),       2.0 * (x * z + w * y)],
        [2.0 * (x * y + w * z),       1.0 - 2.0 * (x**2 + z**2), 2.0 * (y * z - w * x)],
        [2.0 * (x * z - w * y),       2.0 * (y * z + w * x),       1.0 - 2.0 * (x**2 + y**2)]
    ], dtype=np.float64)

    return R


def rotation_matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """
    Converts a 3x3 rotation matrix to unit quaternion [qw, qx, qy, qz] using Shepperd's algorithm.
    """
    tr = np.trace(R)
    if tr > 0.0:
        S = np.sqrt(tr + 1.0) * 2.0
        qw = 0.25 * S
        qx = (R[2, 1] - R[1, 2]) / S
        qy = (R[0, 2] - R[2, 0]) / S
        qz = (R[1, 0] - R[0, 1]) / S
    elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
        S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        qw = (R[2, 1] - R[1, 2]) / S
        qx = 0.25 * S
        qy = (R[0, 1] + R[1, 0]) / S
        qz = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        qw = (R[0, 2] - R[2, 0]) / S
        qx = (R[0, 1] + R[1, 0]) / S
        qy = 0.25 * S
        qz = (R[1, 2] + R[2, 1]) / S
    else:
        S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        qw = (R[1, 0] - R[0, 1]) / S
        qx = (R[0, 2] + R[2, 0]) / S
        qy = (R[1, 2] + R[2, 1]) / S
        qz = 0.25 * S

    return quaternion_normalize(np.array([qw, qx, qy, qz], dtype=np.float64))


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Converts Euler angles (radians, ZYX intrinsic sequence) to unit quaternion [qw, qx, qy, qz].
    """
    cy = np.cos(yaw * 0.5)
    sy = np.sin(yaw * 0.5)
    cp = np.cos(pitch * 0.5)
    sp = np.sin(pitch * 0.5)
    cr = np.cos(roll * 0.5)
    sr = np.sin(roll * 0.5)

    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy

    return quaternion_normalize(np.array([qw, qx, qy, qz], dtype=np.float64))


def quaternion_to_euler(q: np.ndarray) -> Tuple[float, float, float]:
    """
    Converts unit quaternion [qw, qx, qy, qz] to Euler angles (roll, pitch, yaw in radians).
    """
    w, x, y, z = quaternion_normalize(q)

    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x**2 + y**2)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (w * y - z * x)
    if np.abs(sinp) >= 1.0:
        pitch = np.sign(sinp) * (np.pi / 2.0)  # Gimbal lock clamp
    else:
        pitch = np.arcsin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y**2 + z**2)
    yaw = np.arctan2(siny_cosp, cosy_cosp)

    return float(roll), float(pitch), float(yaw)


def euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Converts Euler angles (ZYX convention) directly to 3x3 rotation matrix."""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)

    R_z = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    R_y = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    R_x = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return R_z @ R_y @ R_x


def skew_symmetric(v: np.ndarray) -> np.ndarray:
    """
    Computes 3x3 skew-symmetric matrix [v]_x from 3D vector v = [vx, vy, vz].
    Property: [v]_x @ u = v x u (cross product).
    """
    return np.array([
        [0.0,   -v[2],  v[1]],
        [v[2],   0.0,  -v[0]],
        [-v[1],  v[0],  0.0]
    ], dtype=np.float64)


def quaternion_rotate_vector(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Rotates 3D vector v from body frame to world frame using quaternion q:
    v_w = q * v_b * q^(-1)
    """
    R = quaternion_to_rotation_matrix(q)
    return R @ v


def quaternion_integrate(q: np.ndarray, omega_body: np.ndarray, dt: float) -> np.ndarray:
    """
    Integrates quaternion orientation over time step dt with angular velocity omega (rad/s).
    Uses exact closed-form zero-order hold matrix exponential:
      q(t + dt) = q(t) * exp([0, 0.5 * omega * dt])
    """
    norm_w = np.linalg.norm(omega_body)
    if norm_w < 1e-10:
        # Zero rotation limit
        delta_q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    else:
        angle = norm_w * dt
        axis = omega_body / norm_w
        delta_q = np.array([
            np.cos(0.5 * angle),
            axis[0] * np.sin(0.5 * angle),
            axis[1] * np.sin(0.5 * angle),
            axis[2] * np.sin(0.5 * angle)
        ], dtype=np.float64)

    return quaternion_multiply(q, delta_q)


def create_transform_matrix(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Creates a 4x4 SE(3) transformation matrix from 3x3 rotation R and 3x1 translation t."""
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t.flatten()
    return T


def invert_transform_matrix(T: np.ndarray) -> np.ndarray:
    """
    Inverts a 4x4 SE(3) transformation matrix:
    T_inv = [ R^T , -R^T * t ; 0, 1 ]
    """
    R = T[:3, :3]
    t = T[:3, 3]
    T_inv = np.eye(4, dtype=np.float64)
    R_inv = R.T
    T_inv[:3, :3] = R_inv
    T_inv[:3, 3] = -R_inv @ t
    return T_inv


if __name__ == "__main__":
    print("=== Testing math_utils ===")

    # Test 1: Euler <-> Quaternion round trip
    roll_in, pitch_in, yaw_in = 0.15, -0.25, 1.20
    q = euler_to_quaternion(roll_in, pitch_in, yaw_in)
    roll_out, pitch_out, yaw_out = quaternion_to_euler(q)
    print(f"Euler input:  ({roll_in:.4f}, {pitch_in:.4f}, {yaw_in:.4f})")
    print(f"Euler output: ({roll_out:.4f}, {pitch_out:.4f}, {yaw_out:.4f})")
    assert np.allclose([roll_in, pitch_in, yaw_in], [roll_out, pitch_out, yaw_out], atol=1e-6)

    # Test 2: Rotation Matrix <-> Quaternion round trip
    R = quaternion_to_rotation_matrix(q)
    q_recovered = rotation_matrix_to_quaternion(R)
    # Check quaternion sign equivalence (q and -q represent same rotation)
    assert np.allclose(q, q_recovered, atol=1e-6) or np.allclose(q, -q_recovered, atol=1e-6)

    # Test 3: Skew symmetric cross product
    v1 = np.array([1.0, 2.0, 3.0])
    v2 = np.array([4.0, 5.0, 6.0])
    cross_np = np.cross(v1, v2)
    cross_skew = skew_symmetric(v1) @ v2
    assert np.allclose(cross_np, cross_skew, atol=1e-12)

    # Test 4: Quaternion integration
    omega = np.array([0.0, 0.0, 1.0])  # 1 rad/s yaw rate
    q_init = np.array([1.0, 0.0, 0.0, 0.0])
    q_next = quaternion_integrate(q_init, omega, dt=np.pi / 2.0)  # Rotate 90 deg (pi/2)
    _, _, yaw_integrated = quaternion_to_euler(q_next)
    print(f"Integrated Yaw after pi/2 seconds @ 1 rad/s: {yaw_integrated:.4f} rad (Expected: {np.pi/2:.4f})")
    assert np.isclose(yaw_integrated, np.pi / 2.0, atol=1e-6)

    print("All math_utils tests PASSED successfully!")
