"""Unit tests for Analytics Evaluation, ATE, RPE, Drift, and Orientation Errors."""

import math
import pytest

from app.schemas.trajectory import TrajectoryPoint
from app.repositories.trajectory_repository import trajectory_repository
from app.services.analytics_service import analytics_service, normalize_angle_degrees


def test_angle_normalization_degrees():
    """Test yaw/angle normalization handles wrap-around accurately."""
    # 359 vs 1 deg should be 2 degrees error, NOT 358 degrees
    diff = normalize_angle_degrees(359.0 - 1.0)
    assert diff == -2.0

    # 1 vs 359 deg
    diff2 = normalize_angle_degrees(1.0 - 359.0)
    assert diff2 == 2.0

    # 180 deg
    assert abs(normalize_angle_degrees(180.0)) == 180.0

    # 0 deg
    assert normalize_angle_degrees(0.0) == 0.0


def test_analytics_empty_buffer_returns_insufficient_data():
    """Test empty trajectory buffer returns clean 'INSUFFICIENT DATA' without throwing errors."""
    trajectory_repository.clear()
    metrics = analytics_service.compute_metrics()
    assert metrics.synchronization_status == "INSUFFICIENT DATA"
    assert metrics.sample_count == 0
    assert metrics.localization_error.current is None
    assert metrics.ate.mean is None
    assert metrics.rpe.mean is None
    assert metrics.drift.absolute_meters is None


def test_analytics_ate_rpe_and_drift_calculation():
    """Test accurate computation of Euclidean Error, ATE, RPE, and Drift."""
    trajectory_repository.clear()

    # Generate 4 synchronized points with known offsets
    # GT travels along X axis: (0,0,10) -> (10,0,10) -> (20,0,10) -> (30,0,10) -> traveled dist = 30m
    # EST has constant offset dx=+0.3, dy=+0.4, dz=0.0 -> constant Euclidean error = sqrt(0.3^2 + 0.4^2) = 0.5m
    for i in range(4):
        gt_x = float(i * 10)
        gt = TrajectoryPoint(frame_id=i, timestamp=float(i), x=gt_x, y=0.0, z=10.0, roll=0.0, pitch=0.0, yaw=0.0)
        est = TrajectoryPoint(
            frame_id=i,
            timestamp=float(i),
            x=gt_x + 0.3,
            y=0.4,
            z=10.0,
            roll=1.0,
            pitch=-1.0,
            yaw=2.0,
        )
        trajectory_repository.record_ground_truth(gt)
        trajectory_repository.record_estimated(est)

    metrics = analytics_service.compute_metrics()
    assert metrics.sample_count == 4

    # Localization error
    assert metrics.localization_error.current == pytest.approx(0.5, abs=1e-3)
    assert metrics.localization_error.mean == pytest.approx(0.5, abs=1e-3)
    assert metrics.localization_error.rmse == pytest.approx(0.5, abs=1e-3)
    assert metrics.localization_error.maximum == pytest.approx(0.5, abs=1e-3)
    assert metrics.localization_error.dx == pytest.approx(0.3, abs=1e-3)
    assert metrics.localization_error.dy == pytest.approx(0.4, abs=1e-3)
    assert metrics.localization_error.dz == pytest.approx(0.0, abs=1e-3)

    # ATE
    assert metrics.ate.mean == pytest.approx(0.5, abs=1e-3)
    assert metrics.ate.rmse == pytest.approx(0.5, abs=1e-3)
    assert metrics.ate.sample_count == 4

    # RPE: Since offset is constant (+0.3, +0.4), relative motion of EST matches GT exactly -> RPE = 0.0
    assert metrics.rpe.mean == pytest.approx(0.0, abs=1e-3)
    assert metrics.rpe.sample_count == 3

    # Drift: Traveled distance = 30m, final error = 0.5m -> percentage = (0.5 / 30) * 100 = 1.67%
    assert metrics.drift.absolute_meters == pytest.approx(0.5, abs=1e-3)
    assert metrics.drift.percentage == pytest.approx(1.67, abs=0.1)
    assert metrics.drift.traveled_distance_m == pytest.approx(30.0, abs=0.1)

    # Orientation error
    assert metrics.orientation_error.roll == 1.0
    assert metrics.orientation_error.pitch == -1.0
    assert metrics.orientation_error.yaw == 2.0
