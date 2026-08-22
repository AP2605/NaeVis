"""Integration tests verifying failure isolation, malformed packet resilience, and out-of-order handling."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.camera_service import camera_service
from app.services.frame_sync import frame_synchronizer

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    frame_synchronizer.reset()
    camera_service.reset()
    yield
    frame_synchronizer.reset()
    camera_service.reset()


def test_malformed_p1_packet_does_not_crash_server():
    # 1. Send invalid packet with NaN
    malformed = {
        "frame_id": 1,
        "landmarks": [{"label": "test", "estimated_relative_pos": {"x": "invalid_nan", "y": 0, "z": 0}}],
    }
    resp = client.post("/api/v1/perception/result", json=malformed)
    assert resp.status_code == 422

    # 2. Subsequent valid packet succeeds normally
    valid = {
        "frame_id": 2,
        "timestamp": 0.2,
        "terrain": {"terrain_type": "urban", "confidence": 0.95},
    }
    resp_valid = client.post("/api/v1/perception/result", json=valid)
    assert resp_valid.status_code == 200
    assert resp_valid.json()["frame_id"] == 2


def test_malformed_p2_packet_does_not_crash_server():
    # Missing position
    malformed = {"frame_id": 1, "timestamp": 0.1}
    resp = client.post("/api/v1/simulation/ground-truth", json=malformed)
    assert resp.status_code == 422

    # Subsequent valid packet
    valid = {
        "frame_id": 2,
        "timestamp": 0.2,
        "position": {"x": 5.0, "y": 5.0, "z": 10.0},
    }
    resp_valid = client.post("/api/v1/simulation/ground-truth", json=valid)
    assert resp_valid.status_code == 200


def test_malformed_p3_packet_does_not_crash_server():
    # Missing estimated_pose
    malformed = {"frame_id": 1, "timestamp": 0.1}
    resp = client.post("/api/v1/navigation/state", json=malformed)
    assert resp.status_code == 422

    # Subsequent valid packet
    valid = {
        "frame_id": 2,
        "timestamp": 0.2,
        "estimated_pose": {"x": 5.0, "y": 5.0, "z": 10.0},
    }
    resp_valid = client.post("/api/v1/navigation/state", json=valid)
    assert resp_valid.status_code == 200


def test_failure_isolation_between_sources():
    # P1 sends data
    p1_resp = client.post(
        "/api/v1/perception/result",
        json={"frame_id": 10, "terrain": {"terrain_type": "forest"}},
    )
    assert p1_resp.status_code == 200

    # P3 state can be queried and shows P1 active while P3 is not provided yet
    state_resp = client.get("/api/v1/integration/state")
    assert state_resp.status_code == 200
    data = state_resp.json()
    assert data["perception"] is not None
    assert data["navigation"] is None
    assert data["system_status"]["p1_active"] is True
    assert data["system_status"]["p3_active"] is False


def test_out_of_order_frame_handling():
    # Send frame 10 then frame 5
    client.post(
        "/api/v1/navigation/state",
        json={"frame_id": 10, "timestamp": 1.0, "estimated_pose": {"x": 10, "y": 0, "z": 10}},
    )
    client.post(
        "/api/v1/navigation/state",
        json={"frame_id": 5, "timestamp": 0.5, "estimated_pose": {"x": 5, "y": 0, "z": 10}},
    )

    # State query retrieves both in recent frames sorted
    frames_resp = client.get("/api/v1/integration/frames")
    assert frames_resp.status_code == 200
    frames = frames_resp.json()
    assert len(frames) == 2
    assert frames[0]["frame_id"] == 5
    assert frames[1]["frame_id"] == 10
