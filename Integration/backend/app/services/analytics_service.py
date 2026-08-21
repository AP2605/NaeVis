"""Analytics and Navigation Evaluation Service.

Calculates real-time and aggregate trajectory metrics:
- 3D Euclidean Localization Error and per-axis deltas (ΔX, ΔY, ΔZ)
- Absolute Trajectory Error (ATE: Mean, RMSE, Max)
- Relative Pose Error (RPE: Mean, RMSE)
- Trajectory Drift (Absolute meters & Traveled distance percentage)
- Orientation Angle Errors with normalized 360° yaw wrap-around
"""

import math
import time
from typing import Any

from app.schemas.analytics import (
    AnalyticsResponse,
    AteMetric,
    DriftMetric,
    LocalizationErrorMetric,
    OrientationErrorMetric,
    RpeMetric,
)
from app.schemas.trajectory import TrajectorySyncPair
from app.repositories.trajectory_repository import trajectory_repository


def normalize_angle_degrees(diff_deg: float) -> float:
    """Normalize angular difference into [-180, 180] degrees to handle wrap-around."""
    return ((diff_deg + 180.0) % 360.0) - 180.0


class AnalyticsService:
    """Computes navigation quality and accuracy metrics from synchronized trajectories."""

    def __init__(self):
        self.repo = trajectory_repository

    def compute_metrics(self, limit: int = 500) -> AnalyticsResponse:
        """Compute consolidated evaluation metrics from synchronized trajectory buffer."""
        pairs = self.repo.get_synchronized_pairs(limit=limit)
        n = len(pairs)
        now_ts = time.time()

        if n == 0:
            return AnalyticsResponse(
                localization_error=LocalizationErrorMetric(),
                ate=AteMetric(sample_count=0),
                rpe=RpeMetric(sample_count=0),
                drift=DriftMetric(),
                orientation_error=OrientationErrorMetric(),
                synchronization_status="INSUFFICIENT DATA",
                sample_count=0,
                timestamp=now_ts,
            )

        # 1. Localization Error & ATE calculations
        errors: list[float] = []
        squared_errors: list[float] = []

        for p in pairs:
            if p.ground_truth is not None and p.estimated is not None:
                dx = p.estimated.x - p.ground_truth.x
                dy = p.estimated.y - p.ground_truth.y
                dz = p.estimated.z - p.ground_truth.z
                e = math.sqrt(dx * dx + dy * dy + dz * dz)
                errors.append(e)
                squared_errors.append(e * e)

        latest_pair = pairs[-1]
        cur_gt = latest_pair.ground_truth
        cur_est = latest_pair.estimated

        cur_error = errors[-1] if errors else None
        cur_dx = round(cur_est.x - cur_gt.x, 3) if cur_gt and cur_est else None
        cur_dy = round(cur_est.y - cur_gt.y, 3) if cur_gt and cur_est else None
        cur_dz = round(cur_est.z - cur_gt.z, 3) if cur_gt and cur_est else None

        mean_ate = sum(errors) / len(errors) if errors else None
        rmse_ate = math.sqrt(sum(squared_errors) / len(squared_errors)) if squared_errors else None
        max_ate = max(errors) if errors else None

        loc_metric = LocalizationErrorMetric(
            current=round(cur_error, 4) if cur_error is not None else None,
            mean=round(mean_ate, 4) if mean_ate is not None else None,
            rmse=round(rmse_ate, 4) if rmse_ate is not None else None,
            maximum=round(max_ate, 4) if max_ate is not None else None,
            dx=cur_dx,
            dy=cur_dy,
            dz=cur_dz,
        )

        ate_metric = AteMetric(
            mean=round(mean_ate, 4) if mean_ate is not None else None,
            rmse=round(rmse_ate, 4) if rmse_ate is not None else None,
            maximum=round(max_ate, 4) if max_ate is not None else None,
            sample_count=len(errors),
        )

        # 2. Relative Pose Error (RPE) calculations
        rpe_errors: list[float] = []
        rpe_squared: list[float] = []
        traveled_distance_gt: float = 0.0

        for i in range(len(pairs) - 1):
            p0 = pairs[i]
            p1 = pairs[i + 1]
            if (
                p0.ground_truth is not None
                and p1.ground_truth is not None
                and p0.estimated is not None
                and p1.estimated is not None
            ):
                # GT relative displacement
                d_gt_x = p1.ground_truth.x - p0.ground_truth.x
                d_gt_y = p1.ground_truth.y - p0.ground_truth.y
                d_gt_z = p1.ground_truth.z - p0.ground_truth.z
                step_dist_gt = math.sqrt(d_gt_x * d_gt_x + d_gt_y * d_gt_y + d_gt_z * d_gt_z)
                traveled_distance_gt += step_dist_gt

                # EST relative displacement
                d_est_x = p1.estimated.x - p0.estimated.x
                d_est_y = p1.estimated.y - p0.estimated.y
                d_est_z = p1.estimated.z - p0.estimated.z

                # RPE step translational error
                diff_x = d_est_x - d_gt_x
                diff_y = d_est_y - d_gt_y
                diff_z = d_est_z - d_gt_z
                rpe_e = math.sqrt(diff_x * diff_x + diff_y * diff_y + diff_z * diff_z)
                rpe_errors.append(rpe_e)
                rpe_squared.append(rpe_e * rpe_e)

        if rpe_errors:
            mean_rpe = sum(rpe_errors) / len(rpe_errors)
            rmse_rpe = math.sqrt(sum(rpe_squared) / len(rpe_squared))
            rpe_metric = RpeMetric(
                mean=round(mean_rpe, 4),
                rmse=round(rmse_rpe, 4),
                sample_count=len(rpe_errors),
            )
        else:
            rpe_metric = RpeMetric(mean=None, rmse=None, sample_count=0)

        # 3. Drift metric
        if cur_error is not None and traveled_distance_gt > 0.05:
            drift_pct = (cur_error / traveled_distance_gt) * 100.0
            drift_metric = DriftMetric(
                absolute_meters=round(cur_error, 4),
                percentage=round(drift_pct, 2),
                traveled_distance_m=round(traveled_distance_gt, 2),
            )
        elif cur_error is not None:
            drift_metric = DriftMetric(
                absolute_meters=round(cur_error, 4),
                percentage=0.0,
                traveled_distance_m=round(traveled_distance_gt, 2),
            )
        else:
            drift_metric = DriftMetric()

        # 4. Orientation error calculations
        if cur_gt is not None and cur_est is not None:
            roll_err = normalize_angle_degrees(cur_est.roll - cur_gt.roll)
            pitch_err = normalize_angle_degrees(cur_est.pitch - cur_gt.pitch)
            yaw_err = normalize_angle_degrees(cur_est.yaw - cur_gt.yaw)
            orient_metric = OrientationErrorMetric(
                roll=round(roll_err, 2),
                pitch=round(pitch_err, 2),
                yaw=round(yaw_err, 2),
            )
        else:
            orient_metric = OrientationErrorMetric()

        # Sync Status Evaluation
        sync_status = "SYNCED" if n >= 5 else "PARTIAL"

        return AnalyticsResponse(
            localization_error=loc_metric,
            ate=ate_metric,
            rpe=rpe_metric,
            drift=drift_metric,
            orientation_error=orient_metric,
            synchronization_status=sync_status,
            sample_count=n,
            timestamp=now_ts,
        )


analytics_service = AnalyticsService()
