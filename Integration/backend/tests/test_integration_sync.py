"""Tests for Frame Synchronization and Unified State Integration."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_integration_multi_source_synchronization():
    """Test that packets from P1, P2, and P3 for frame_id=200 align into one IntegratedFrame."""
    # Reset before test
    client.post("/api/v1/integration/reset")

    # Ingest P2 Ground Truth for frame 200
    p2_data = {
        "timestamp": 10.0,
        "frame_id": 200,
        "position": {"x": 50.0, "y": 20.0, "z": 15.0},
        "orientation": {"roll": 1.0, "pitch": -1.0, "yaw": 45.0},
    }
    client.post("/api/v1/simulation/ground-truth", json=p2_data)

    # Ingest P3 Navigation for frame 200
    p3_data = {
        "frame_id": 200,
        "timestamp": 10.0,
        "estimated_pose": {"x": 50.1, "y": 19.9, "z": 15.05, "roll": 1.1, "pitch": -0.9, "yaw": 45.2},
        "velocity": {"x": 2.0, "y": 0.5, "z": 0.0},
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.97,
    }
    client.post("/api/v1/navigation/state", json=p3_data)

    # Ingest P1 Perception for frame 200
    p1_data = {
        "frame_id": 200,
        "timestamp": 10.0,
        "terrain": {"terrain_type": "suburban", "confidence": 0.92},
        "landmarks": [{"landmark_id": "LM_99", "label": "roof", "confidence": 0.89}],
    }
    client.post("/api/v1/perception/result", json=p1_data)

    # Query synchronized frame 200
    frame_resp = client.get("/api/v1/integration/frames/200")
    assert frame_resp.status_code == 200
    frame = frame_resp.json()
    assert frame["frame_id"] == 200
    assert frame["ground_truth"] is not None
    assert frame["ground_truth"]["position"]["x"] == 50.0
    assert frame["navigation"] is not None
    assert frame["navigation"]["estimated_pose"]["x"] == 50.1
    assert frame["perception"] is not None
    assert frame["perception"]["terrain"]["terrain_type"] == "suburban"
    assert set(frame["sync_sources"]) == {"p1", "p2", "p3"}


def test_integrated_state_endpoint():
    """Test GET /api/v1/integration/state returns latest composite state."""
    resp = client.get("/api/v1/integration/state")
    assert resp.status_code == 200
    state = resp.json()
    assert state["current_frame_id"] == 200
    assert state["navigation"] is not None
    assert state["ground_truth"] is not None
    assert state["perception"] is not None
    assert "sync_status" in state
    assert "system_status" in state


def test_partial_module_tolerance():
    """Test that when only P3 sends data for a new frame, system operates normally."""
    p3_data = {
        "frame_id": 305,
        "timestamp": 15.25,
        "estimated_pose": {"x": 80.0, "y": 40.0, "z": 22.0},
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.95,
    }
    resp = client.post("/api/v1/navigation/state", json=p3_data)
    assert resp.status_code == 200

    frame_resp = client.get("/api/v1/integration/frames/305")
    assert frame_resp.status_code == 200
    frame = frame_resp.json()
    assert frame["frame_id"] == 305
    assert frame["navigation"] is not None
    assert frame["ground_truth"] is None
    assert frame["perception"] is None
    assert frame["sync_sources"] == ["p3"]


def test_frame_not_found_404():
    """Test querying non-existent frame returns 404."""
    resp = client.get("/api/v1/integration/frames/99999")
    assert resp.status_code == 404


def test_recent_frames_list():
    """Test GET /api/v1/integration/frames returns list of buffered frames."""
    resp = client.get("/api/v1/integration/frames?limit=10")
    assert resp.status_code == 200
    frames = resp.json()
    assert isinstance(frames, list)
    assert len(frames) >= 2
