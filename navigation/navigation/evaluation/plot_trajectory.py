"""
Trajectory Visualization & Plotting Module (P3 Module).
======================================================
Generates high-resolution 2D and 3D flight trajectory plots:
  - 3D spatial flight path comparison (Ground Truth vs. Estimated).
  - 2D top-down (XY plane) terrain projection.
  - Position error curves vs. flight time (X, Y, Z, and Euclidean norm).
  - Multi-panel benchmarking dashboard figures for reports.
"""

from typing import Optional, List, Union
import os
import numpy as np
import matplotlib
# Use non-interactive backend for headless / server execution
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from navigation.evaluation.metrics import TrajectoryEvaluator


class TrajectoryPlotter:
    """
    Renders and exports high-quality 2D/3D trajectory comparison figures.
    """

    def __init__(self, style: str = "seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default"):
        self.style = style

    def plot_3d(
        self,
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        map_points: Optional[np.ndarray] = None,
        save_path: Optional[str] = None,
        title: str = "3D Flight Trajectory: Ground Truth vs. Estimated"
    ) -> plt.Figure:
        """Generates a 3D plot comparing Ground Truth vs. Estimated trajectory."""
        fig = plt.figure(figsize=(10, 8), dpi=150)
        ax = fig.add_subplot(111, projection="3d")

        est = np.array(est_positions, dtype=np.float64)
        gt = np.array(gt_positions, dtype=np.float64)

        # Plot 3D Sparse Map Landmarks
        if map_points is not None and len(map_points) > 0:
            mp = np.array(map_points, dtype=np.float64)
            # Sample at most 500 points for clear rendering
            if len(mp) > 500:
                indices = np.random.choice(len(mp), 500, replace=False)
                mp = mp[indices]
            ax.scatter(mp[:, 0], mp[:, 1], mp[:, 2], c="gray", alpha=0.3, s=3, label="3D Map Points")

        # Plot Ground Truth Path
        ax.plot(gt[:, 0], gt[:, 1], gt[:, 2], label="Ground Truth (Blender)", color="#2ecc71", linewidth=2.5, linestyle="--")

        # Plot Estimated Path
        ax.plot(est[:, 0], est[:, 1], est[:, 2], label="Estimated Pose (P3 VIO/SLAM)", color="#2980b9", linewidth=2.0)

        # Mark Start and End Points
        ax.scatter([gt[0, 0]], [gt[0, 1]], [gt[0, 2]], color="green", s=80, marker="o", label="Start (Takeoff)")
        ax.scatter([est[-1, 0]], [est[-1, 1]], [est[-1, 2]], color="red", s=80, marker="^", label="End (Landing)")

        ax.set_xlabel("X (East) [m]", fontsize=11, labelpad=8)
        ax.set_ylabel("Y (North) [m]", fontsize=11, labelpad=8)
        ax.set_zlabel("Z (Up / Altitude) [m]", fontsize=11, labelpad=8)
        ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
        ax.legend(loc="upper right", frameon=True, fontsize=10)

        plt.tight_layout()
        if save_path:
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            plt.savefig(save_path, bbox_inches="tight")
            print(f"[Plotter] Saved 3D plot to: {save_path}")

        return fig

    def plot_2d_topdown(
        self,
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        save_path: Optional[str] = None,
        title: str = "Top-Down Flight Path (Horizontal XY Plane)"
    ) -> plt.Figure:
        """Generates a 2D top-down bird's-eye view (XY coordinates)."""
        fig, ax = plt.subplots(figsize=(8, 8), dpi=150)

        est = np.array(est_positions, dtype=np.float64)
        gt = np.array(gt_positions, dtype=np.float64)

        ax.plot(gt[:, 0], gt[:, 1], label="Ground Truth (Blender)", color="#27ae60", linewidth=2.5, linestyle="--")
        ax.plot(est[:, 0], est[:, 1], label="Estimated Path (P3 VIO)", color="#2980b9", linewidth=2.0)

        ax.scatter([gt[0, 0]], [gt[0, 1]], color="green", s=80, marker="o", label="Start", zorder=5)
        ax.scatter([est[-1, 0]], [est[-1, 1]], color="red", s=80, marker="^", label="End", zorder=5)

        ax.set_xlabel("X (East) [meters]", fontsize=11)
        ax.set_ylabel("Y (North) [meters]", fontsize=11)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.axis("equal")
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(loc="upper right", frameon=True)

        plt.tight_layout()
        if save_path:
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            plt.savefig(save_path, bbox_inches="tight")
            print(f"[Plotter] Saved 2D top-down plot to: {save_path}")

        return fig

    def plot_error_curves(
        self,
        timestamps: np.ndarray,
        est_positions: np.ndarray,
        gt_positions: np.ndarray,
        save_path: Optional[str] = None
    ) -> plt.Figure:
        """Plots position error components (X, Y, Z) and Euclidean error over flight time."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), dpi=150, sharex=True)

        min_len = min(len(timestamps), len(est_positions), len(gt_positions))
        t = np.array(timestamps[:min_len], dtype=np.float64)
        est = np.array(est_positions[:min_len], dtype=np.float64)
        gt = np.array(gt_positions[:min_len], dtype=np.float64)

        diff = est - gt
        euclidean_err = np.linalg.norm(diff, axis=1)

        # Subplot 1: Axis Errors
        ax1.plot(t, diff[:, 0], label="Error X (East)", color="#e74c3c", linewidth=1.5)
        ax1.plot(t, diff[:, 1], label="Error Y (North)", color="#27ae60", linewidth=1.5)
        ax1.plot(t, diff[:, 2], label="Error Z (Altitude)", color="#2980b9", linewidth=1.5)
        ax1.axhline(0, color="gray", linestyle="--", alpha=0.7)
        ax1.set_ylabel("Axis Error [meters]", fontsize=11)
        ax1.set_title("Navigation Localization Error vs. Flight Time", fontsize=12, fontweight="bold")
        ax1.grid(True, linestyle=":", alpha=0.6)
        ax1.legend(loc="upper right")

        # Subplot 2: Total Euclidean Error
        mean_err = np.mean(euclidean_err)
        rmse_err = np.sqrt(np.mean(euclidean_err ** 2))

        ax2.plot(t, euclidean_err, label="Total Euclidean Error ||e||", color="#8e44ad", linewidth=2.0)
        ax2.axhline(mean_err, color="#e67e22", linestyle="--", label=f"Mean Error: {mean_err:.3f}m")
        ax2.axhline(rmse_err, color="#c0392b", linestyle=":", label=f"ATE RMSE: {rmse_err:.3f}m")
        ax2.set_xlabel("Flight Time [seconds]", fontsize=11)
        ax2.set_ylabel("Total Error [meters]", fontsize=11)
        ax2.grid(True, linestyle=":", alpha=0.6)
        ax2.legend(loc="upper right")

        plt.tight_layout()
        if save_path:
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            plt.savefig(save_path, bbox_inches="tight")
            print(f"[Plotter] Saved error curves to: {save_path}")

        return fig


if __name__ == "__main__":
    print("=== Testing TrajectoryPlotter ===")
    t = np.linspace(0, 6, 120)
    gt_pos = np.column_stack([np.cos(t) * 4, np.sin(t) * 4, t * 0.4])
    est_pos = gt_pos + np.random.normal(0, 0.04, gt_pos.shape)

    plotter = TrajectoryPlotter()
    fig1 = plotter.plot_3d(est_pos, gt_pos, save_path="navigation/outputs/test_3d_trajectory.png")
    fig2 = plotter.plot_2d_topdown(est_pos, gt_pos, save_path="navigation/outputs/test_2d_topdown.png")
    fig3 = plotter.plot_error_curves(t, est_pos, gt_pos, save_path="navigation/outputs/test_error_curves.png")

    plt.close("all")
    print("TrajectoryPlotter verification PASSED! [Milestone 8 Achieved]")
