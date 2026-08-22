"""Unit and Integration tests for Source Health, Stale Detection, and Diagnostics."""

import time
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas.p1 import P1VisionResult, TerrainResult
from app.schemas.p2 import SimulationGroundTruthPacket
from app.schemas.p3 import NavigationStatePacket, EstimatedPose
from app.schemas.common import Position3D
from app.services.camera_service import camera_service
from app.services.frame_sync import frame_synchronizer

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all synchronization and camera services before each test."""
    frame_synchronizer.reset()
    camera_service.reset()
    yield
    frame_synchronizer.reset()
    camera_service.reset()


def test_initial_source_health_is_disconnected():
    health = frame_synchronizer.get_source_health()
    assert health["p1"]["state"] == "DISCONNECTED"
    assert health["p2"]["state"] == "DISCONNECTED"
    assert health["p3"]["state"] == "DISCONNECTED"
    assert health["camera"]["state"] == "DISCONNECTED"


def test_source_health_transitions_to_connected_and_stale():
    # 1. Ingest real P1 packet
    p1_packet = P1VisionResult(
        frame_id=1,
        timestamp=0.1,
        terrain=TerrainResult(terrain_type="urban", confidence=0.9),
    )
    frame_synchronizer.ingest_p1(p1_packet, is_real=True)

    # Ingest mock P2 packet
    p2_packet = SimulationGroundTruthPacket(
        frame_id=1,
        timestamp=0.1,
        position=Position3D(x=0.0, y=0.0, z=10.0),
    )
    frame_synchronizer.ingest_p2(p2_packet, is_real=False)

    health = frame_synchronizer.get_source_health()
    assert health["p1"]["state"] == "CONNECTED"
    assert health["p1"]["is_real"] is True
    assert health["p2"]["state"] == "MOCK"
    assert health["p2"]["is_real"] is False

    # 2. Simulate stale timeout by advancing last packet time back
    frame_synchronizer._last_p1_time = time.time() - (settings.STALE_TIMEOUT_SEC + 1.0)
    health_stale = frame_synchronizer.get_source_health()
    assert health_stale["p1"]["state"] == "STALE"


def test_integration_health_endpoint():
    # Ingest P3 packet
    p3_packet = {
        "frame_id": 5,
        "timestamp": 0.5,
        "estimated_pose": {"x": 1.0, "y": 2.0, "z": 10.0},
    }
    resp = client.post("/api/v1/navigation/state?source=real", json=p3_packet)
    assert resp.status_code == 200
    assert resp.json()["is_real"] is True

    # Query health endpoint
    health_resp = client.get("/api/v1/integration/health")
    assert health_resp.status_code == 200
    data = health_resp.json()
    assert data["p3"]["state"] == "CONNECTED"
    assert data["p3"]["is_real"] is True
    assert data["p3"]["last_frame_id"] == 5


def test_camera_health_and_stats_endpoint():
    stats_resp = client.get("/api/v1/integration/camera/stats")
    assert stats_resp.status_code == 200
    data = stats_resp.json()
    assert "fps" in data
    assert "health" in data
    assert data["health"]["state"] == "DISCONNECTED"
