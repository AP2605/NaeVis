"""Unit and endpoint tests for Trajectory storage and retrieval."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.trajectory import TrajectoryPoint
from app.repositories.trajectory_repository import trajectory_repository

client = TestClient(app)


def test_trajectory_repository_storage_and_limit():
    """Test trajectory points are recorded and bounded by MAX_TRAJECTORY_POINTS."""
    trajectory_repository.clear()
    
    # Store 10 points
    for i in range(10):
        gt = TrajectoryPoint(frame_id=i, timestamp=float(i), x=float(i), y=0.0, z=10.0)
        est = TrajectoryPoint(frame_id=i, timestamp=float(i), x=float(i) + 0.1, y=0.1, z=10.0)
        trajectory_repository.record_ground_truth(gt)
        trajectory_repository.record_estimated(est)

    data = trajectory_repository.get_trajectory(limit=5)
    assert len(data.ground_truth) == 5
    assert len(data.estimated) == 5
    assert data.sample_count == 5


def test_trajectory_endpoint_retrieval():
    """Test GET /api/v1/trajectory endpoint."""
    trajectory_repository.clear()
    
    gt = TrajectoryPoint(frame_id=100, timestamp=10.0, x=5.0, y=6.0, z=7.0)
    est = TrajectoryPoint(frame_id=100, timestamp=10.0, x=5.2, y=6.1, z=7.0)
    trajectory_repository.record_ground_truth(gt)
    trajectory_repository.record_estimated(est)

    res = client.get("/api/v1/trajectory?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert "ground_truth" in data
    assert "estimated" in data
    assert len(data["ground_truth"]) >= 1
    assert data["ground_truth"][-1]["frame_id"] == 100
    assert data["estimated"][-1]["frame_id"] == 100
