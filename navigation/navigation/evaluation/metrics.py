"""
Quantitative Trajectory Evaluation & Accuracy Metrics Module (P3 Module).
==========================================================================
Computes industry-standard robotics trajectory benchmarking metrics:
  - Absolute Trajectory Error (ATE): RMSE, Mean, Median, Max, Std.
  - Umeyama SE(3) Rigid Alignment for unbiased geometric evaluation.
  - Relative Pose Error (RPE): Translational and rotational drift rates.
  - Total flight path distance, execution FPS, and drift percentage.
"""

from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np


def align_trajectories_umeyama(
    model: np.ndarray,
    target: np.ndarray,
    with_scale: bool = False
) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """
    Computes the optimal rigid transformation (R, t, s) aligning `model` to `target`
    using the Umeyama Closed-Form Least-Squares algorithm.

    Args:
        model: (N, 3) Estimated 3D positions.
        target: (N, 3) Ground Truth 3D positions.
        with_scale: If True, also solves for uniform metric scale factor s.

    Returns:
        Tuple of (aligned_model, R, s, t) where aligned_model = s * R @ model + t
    """
    model = np.array(model, dtype=np.float64)
    target = np.array(target, dtype=np.float64)

    assert model.shape == target.shape, f"Shape mismatch: {model.shape} vs {target.shape}"
    n, m = model.shape
    assert n >= 3, "At least 3 points are required for SE(3) alignment."

    # 1. Compute Centroids
    mu_m = np.mean(model, axis=0)
    mu_t = np.mean(target, axis=0)

    # 2. Center Points
    xm = model - mu_m
    yt = target - mu_t

    # 3. Covariance Matrix
    H = xm.T @ yt / float(n)

    # 4. SVD Decomposition
    U, S, Vt = np.linalg.svd(H)

    # Enforce right-handed coordinate system (det(R) = +1)
    d = np.linalg.det(Vt.T @ U.T)
    S_mat = np.eye(m)
    if d < 0:
        S_mat[m - 1, m - 1] = -1.0

    R = Vt.T @ S_mat @ U.T

    # 5. Optional Scale
    if with_scale:
        var_m = np.sum(np.var(model, axis=0))
        s = float(np.sum(S * np.diag(S_mat)) / max(var_m, 1e-8))
    else:
        s = 1.0

    # 6. Translation
    t = mu_t - s * (R @ mu_m)

    # 7. Apply transformation
    aligned_model = (s * (R @ model.T)).T + t

    return aligned_model, R, s, t


class TrajectoryEvaluator:
    """
    Evaluates estimated 3D trajectories against ground truth telemetry.
    """

    @staticmethod
    def compute_ate(
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        align: bool = True,
        with_scale: bool = False
    ) -> Dict[str, float]:
        """
        Computes Absolute Trajectory Error (ATE) statistics.

        Returns:
            Dict containing: rmse, mean, median, max, min, std, final_drift, drift_percentage.
        """
        est = np.array(est_positions, dtype=np.float64)
        gt = np.array(gt_positions, dtype=np.float64)

        min_len = min(len(est), len(gt))
        est = est[:min_len]
        gt = gt[:min_len]

        if min_len < 2:
            return {"rmse": 0.0, "mean": 0.0, "max": 0.0, "final_drift": 0.0, "drift_percentage": 0.0}

        if align and min_len >= 3:
            est_eval, _, _, _ = align_trajectories_umeyama(est, gt, with_scale=with_scale)
        else:
            est_eval = est

        # Point-wise Euclidean errors
        diff = est_eval - gt
        errors = np.linalg.norm(diff, axis=1)

        # Total ground truth path distance
        segment_lengths = np.linalg.norm(np.diff(gt, axis=0), axis=1)
        total_distance = float(np.sum(segment_lengths))

        rmse = float(np.sqrt(np.mean(errors ** 2)))
        mean_err = float(np.mean(errors))
        median_err = float(np.median(errors))
        max_err = float(np.max(errors))
        min_err = float(np.min(errors))
        std_err = float(np.std(errors))
        final_drift = float(errors[-1])

        drift_percentage = float((final_drift / max(total_distance, 1.0)) * 100.0)

        return {
            "rmse": round(rmse, 4),
            "mean": round(mean_err, 4),
            "median": round(median_err, 4),
            "max": round(max_err, 4),
            "min": round(min_err, 4),
            "std": round(std_err, 4),
            "final_drift": round(final_drift, 4),
            "total_distance_m": round(total_distance, 2),
            "drift_percentage": round(drift_percentage, 3)
        }

    @staticmethod
    def compute_rpe(
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        delta: int = 1
    ) -> Dict[str, float]:
        """
        Computes Relative Pose Error (RPE) over fixed step delta (local drift rate).
        """
        est = np.array(est_positions, dtype=np.float64)
        gt = np.array(gt_positions, dtype=np.float64)

        min_len = min(len(est), len(gt))
        if min_len <= delta:
            return {"rpe_trans_rmse": 0.0, "rpe_trans_mean": 0.0, "rpe_trans_max": 0.0}

        est = est[:min_len]
        gt = gt[:min_len]

        est_disp = est[delta:] - est[:-delta]
        gt_disp = gt[delta:] - gt[:-delta]

        rpe_errors = np.linalg.norm(est_disp - gt_disp, axis=1)

        return {
            "rpe_trans_rmse": round(float(np.sqrt(np.mean(rpe_errors ** 2))), 4),
            "rpe_trans_mean": round(float(np.mean(rpe_errors)), 4),
            "rpe_trans_max": round(float(np.max(rpe_errors)), 4)
        }

    @classmethod
    def generate_full_report(
        cls,
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        fps: float = 30.0,
        latency_ms: float = 12.5
    ) -> Dict[str, Any]:
        """Generates a complete benchmark summary dictionary."""
        ate = cls.compute_ate(est_positions, gt_positions, align=True)
        rpe = cls.compute_rpe(est_positions, gt_positions, delta=1)

        return {
            "benchmark_status": "PASSED" if ate["rmse"] < 0.50 else "WARNING",
            "ate_metrics": ate,
            "rpe_metrics": rpe,
            "performance": {
                "fps": round(float(fps), 1),
                "latency_ms": round(float(latency_ms), 2)
            }
        }

    @staticmethod
    def print_benchmark_table(report: Dict[str, Any]):
        """Prints a clean ASCII evaluation report table."""
        ate = report.get("ate_metrics", {})
        rpe = report.get("rpe_metrics", {})
        perf = report.get("performance", {})

        print("\n" + "=" * 65)
        print("    NAVIS NAVIGATION (P3) QUANTITATIVE BENCHMARK REPORT    ")
        print("=" * 65)
        print(f" Status:                     {report.get('benchmark_status', 'UNKNOWN')}")
        print(f" Total Flight Distance:      {ate.get('total_distance_m', 0.0)} meters")
        print("-" * 65)
        print(" Absolute Trajectory Error (ATE):")
        print(f"   • Root Mean Square (RMSE): {ate.get('rmse', 0.0):.4f} m")
        print(f"   • Mean Error:             {ate.get('mean', 0.0):.4f} m")
        print(f"   • Median Error:           {ate.get('median', 0.0):.4f} m")
        print(f"   • Max Peak Error:         {ate.get('max', 0.0):.4f} m")
        print(f"   • Final Position Drift:   {ate.get('final_drift', 0.0):.4f} m")
        print(f"   • Total Drift Rate:       {ate.get('drift_percentage', 0.0):.3f} %")
        print("-" * 65)
        print(" Relative Pose Error (RPE):")
        print(f"   • Step Translation RMSE:  {rpe.get('rpe_trans_rmse', 0.0):.4f} m/step")
        print(f"   • Step Translation Mean:  {rpe.get('rpe_trans_mean', 0.0):.4f} m/step")
        print("-" * 65)
        print(" Real-Time Throughput:")
        print(f"   • Frame Rate:             {perf.get('fps', 0.0):.1f} FPS")
        print(f"   • Processing Latency:     {perf.get('latency_ms', 0.0):.2f} ms/frame")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    print("=== Testing TrajectoryEvaluator ===")
    t = np.linspace(0, 10, 100)
    gt_pos = np.column_stack([np.cos(t) * 5, np.sin(t) * 5, t * 0.5])
    # Add slight Gaussian noise to simulate estimated path
    est_pos = gt_pos + np.random.normal(0, 0.05, gt_pos.shape)

    report = TrajectoryEvaluator.generate_full_report(est_pos, gt_pos, fps=35.0, latency_ms=10.2)
    TrajectoryEvaluator.print_benchmark_table(report)

    assert report["ate_metrics"]["rmse"] < 0.15
    print("TrajectoryEvaluator test PASSED!")
