"""
Unit Tests for Trajectory Evaluation & Plotting (metrics.py, plot_trajectory.py).
"""

import unittest
import os
import tempfile
import numpy as np

from navigation.evaluation.metrics import TrajectoryEvaluator, align_trajectories_umeyama
from navigation.evaluation.plot_trajectory import TrajectoryPlotter


class TestEvaluation(unittest.TestCase):

    def test_ate_identical_trajectories(self):
        t = np.linspace(0, 5, 50)
        gt_pos = np.column_stack([np.cos(t), np.sin(t), t])
        est_pos = gt_pos.copy()

        ate = TrajectoryEvaluator.compute_ate(est_pos, gt_pos, align=False)
        self.assertAlmostEqual(ate["rmse"], 0.0, places=4)
        self.assertAlmostEqual(ate["mean"], 0.0, places=4)
        self.assertAlmostEqual(ate["final_drift"], 0.0, places=4)
        self.assertAlmostEqual(ate["drift_percentage"], 0.0, places=4)

    def test_ate_known_offset(self):
        gt_pos = np.zeros((20, 3))
        est_pos = np.full((20, 3), [0.3, 0.4, 0.0]) # Euclidean offset = 0.5m

        ate = TrajectoryEvaluator.compute_ate(est_pos, gt_pos, align=False)
        self.assertAlmostEqual(ate["rmse"], 0.5, places=3)
        self.assertAlmostEqual(ate["mean"], 0.5, places=3)
        self.assertAlmostEqual(ate["final_drift"], 0.5, places=3)

    def test_umeyama_alignment(self):
        # Create true circle
        t = np.linspace(0, 2 * np.pi, 30)
        gt = np.column_stack([np.cos(t) * 3, np.sin(t) * 3, np.zeros_like(t)])

        # Apply 90-degree yaw rotation and (2, 3, 1) translation
        R_rot = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float64)
        t_shift = np.array([2.0, 3.0, 1.0])
        model = (R_rot @ gt.T).T + t_shift

        aligned, R_est, _, t_est = align_trajectories_umeyama(model, gt)
        res_error = np.mean(np.linalg.norm(aligned - gt, axis=1))

        self.assertAlmostEqual(res_error, 0.0, places=4)
        self.assertTrue(np.allclose(R_est @ R_rot, np.eye(3), atol=1e-3))

    def test_rpe_calculation(self):
        gt = np.column_stack([np.arange(10), np.zeros(10), np.zeros(10)]) # 1.0 m/step
        est = np.column_stack([np.arange(10) * 1.1, np.zeros(10), np.zeros(10)]) # 1.1 m/step

        rpe = TrajectoryEvaluator.compute_rpe(est, gt, delta=1)
        self.assertAlmostEqual(rpe["rpe_trans_mean"], 0.1, places=3)

    def test_plotter_exports(self):
        t = np.linspace(0, 3, 30)
        gt = np.column_stack([np.cos(t), np.sin(t), t * 0.2])
        est = gt + np.random.normal(0, 0.02, gt.shape)

        plotter = TrajectoryPlotter()
        with tempfile.TemporaryDirectory() as tmpdir:
            p3d = os.path.join(tmpdir, "test_3d.png")
            p2d = os.path.join(tmpdir, "test_2d.png")
            perr = os.path.join(tmpdir, "test_err.png")

            plotter.plot_3d(est, gt, save_path=p3d)
            plotter.plot_2d_topdown(est, gt, save_path=p2d)
            plotter.plot_error_curves(t, est, gt, save_path=perr)

            self.assertTrue(os.path.exists(p3d) and os.path.getsize(p3d) > 1000)
            self.assertTrue(os.path.exists(p2d) and os.path.getsize(p2d) > 1000)
            self.assertTrue(os.path.exists(perr) and os.path.getsize(perr) > 1000)


if __name__ == "__main__":
    unittest.main()
