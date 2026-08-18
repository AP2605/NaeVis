"""
Unit Tests for Math & Geometric Utilities (math_utils.py).
"""

import unittest
import numpy as np

from navigation.utils.math_utils import (
    quaternion_normalize,
    quaternion_conjugate,
    quaternion_multiply,
    quaternion_to_rotation_matrix,
    rotation_matrix_to_quaternion,
    euler_to_quaternion,
    quaternion_to_euler,
    euler_to_rotation_matrix,
    skew_symmetric,
    quaternion_rotate_vector,
    quaternion_integrate,
    create_transform_matrix,
    invert_transform_matrix
)


class TestMathUtils(unittest.TestCase):

    def test_quaternion_normalization(self):
        q = np.array([2.0, 0.0, 0.0, 0.0])
        q_norm = quaternion_normalize(q)
        self.assertAlmostEqual(np.linalg.norm(q_norm), 1.0, places=7)
        self.assertTrue(np.allclose(q_norm, [1.0, 0.0, 0.0, 0.0]))

        # Zero vector handling
        q_zero = np.array([0.0, 0.0, 0.0, 0.0])
        self.assertTrue(np.allclose(quaternion_normalize(q_zero), [1.0, 0.0, 0.0, 0.0]))

    def test_quaternion_conjugate(self):
        q = np.array([0.5, 0.5, 0.5, 0.5])
        q_conj = quaternion_conjugate(q)
        self.assertTrue(np.allclose(q_conj, [0.5, -0.5, -0.5, -0.5]))

        # q * q_conj = [1, 0, 0, 0] (Identity)
        q_identity = quaternion_multiply(q, q_conj)
        self.assertTrue(np.allclose(q_identity, [1.0, 0.0, 0.0, 0.0], atol=1e-6))

    def test_quaternion_multiplication(self):
        # 90 deg rotation around X times 90 deg rotation around Y
        q_x = euler_to_quaternion(np.pi / 2, 0.0, 0.0)
        q_y = euler_to_quaternion(0.0, np.pi / 2, 0.0)
        q_combined = quaternion_multiply(q_x, q_y)

        # Rotate vector [0, 0, 1] by combined rotation
        v = np.array([0.0, 0.0, 1.0])
        v_rot = quaternion_rotate_vector(q_combined, v)
        self.assertTrue(np.allclose(np.linalg.norm(v_rot), 1.0))

    def test_euler_quaternion_roundtrip(self):
        test_cases = [
            (0.0, 0.0, 0.0),
            (0.2, -0.4, 1.1),
            (-0.8, 0.5, -2.3),
            (np.pi / 4, -np.pi / 6, np.pi / 3),
            (0.0, np.pi / 2 - 0.01, 0.0)  # Near gimbal lock
        ]

        for roll_in, pitch_in, yaw_in in test_cases:
            q = euler_to_quaternion(roll_in, pitch_in, yaw_in)
            roll_out, pitch_out, yaw_out = quaternion_to_euler(q)
            self.assertAlmostEqual(roll_in, roll_out, places=5, msg=f"Failed for roll {roll_in}")
            self.assertAlmostEqual(pitch_in, pitch_out, places=5, msg=f"Failed for pitch {pitch_in}")
            self.assertAlmostEqual(yaw_in, yaw_out, places=5, msg=f"Failed for yaw {yaw_in}")

    def test_rotation_matrix_quaternion_roundtrip(self):
        angles = [(0.1, 0.2, 0.3), (-0.5, 0.2, -1.0), (0.0, 0.0, np.pi)]
        for r, p, y in angles:
            q_in = euler_to_quaternion(r, p, y)
            R = quaternion_to_rotation_matrix(q_in)
            q_out = rotation_matrix_to_quaternion(R)

            # Check equivalence (q and -q represent same SO(3) rotation)
            match_pos = np.allclose(q_in, q_out, atol=1e-6)
            match_neg = np.allclose(q_in, -q_out, atol=1e-6)
            self.assertTrue(match_pos or match_neg)

    def test_skew_symmetric(self):
        v = np.array([1.5, -2.3, 4.1])
        u = np.array([0.5, 1.2, -0.8])
        cross_standard = np.cross(v, u)
        cross_skew = skew_symmetric(v) @ u
        self.assertTrue(np.allclose(cross_standard, cross_skew, atol=1e-10))

    def test_quaternion_integrate(self):
        # 180 degree rotation around Z in 2 seconds (w = [0, 0, pi/2])
        w = np.array([0.0, 0.0, np.pi / 2])
        q0 = np.array([1.0, 0.0, 0.0, 0.0])
        q_final = quaternion_integrate(q0, w, dt=2.0)
        _, _, yaw = quaternion_to_euler(q_final)
        self.assertAlmostEqual(abs(yaw), np.pi, places=5)

    def test_transform_matrix_inversion(self):
        R = euler_to_rotation_matrix(0.3, -0.2, 1.4)
        t = np.array([10.5, -3.2, 4.8])
        T = create_transform_matrix(R, t)
        T_inv = invert_transform_matrix(T)

        # T * T_inv = Identity(4)
        I4 = T @ T_inv
        self.assertTrue(np.allclose(I4, np.eye(4), atol=1e-7))


if __name__ == "__main__":
    unittest.main()
