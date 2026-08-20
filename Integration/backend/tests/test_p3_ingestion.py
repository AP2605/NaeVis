"""Tests for P3 Navigation State ingestion and validation."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_valid_p3_navigation_ingestion():
    """Test valid P3 navigation packet is ingested correctly."""
    payload = {
        "frame_id": 125,
        "timestamp": 4.166,
        "estimated_pose": {
            "x": 10.42,
            "y": 5.81,
            "z": 20.13,
            "roll": 0.3,
            "pitch": 1.1,
            "yaw": 89.7,
        },
        "velocity": {
            "x": 3.2,
            "y": 0.0,
            "z": 0.1,
        },
        "tracking_state": "TRACKING_GOOD",
        "confidence": 0.96,
        "processing_time_ms": 18.0,
    }

    response = client.post("/api/v1/navigation/state", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["frame_id"] == 125
    assert "p3" in res_data["sync_sources"]

    # Verify latest navigation state endpoint
    latest_resp = client.get("/api/v1/navigation/state/latest")
    assert latest_resp.status_code == 200
    latest_data = latest_resp.json()
    assert latest_data["frame_id"] == 125
    assert latest_data["estimated_pose"]["x"] == 10.42
    assert latest_data["confidence"] == 0.96
    assert latest_data["tracking_state"] == "TRACKING_GOOD"


def test_invalid_p3_navigation_rejected():
    """Test invalid confidence or missing pose is rejected with HTTP 422."""
    # Test confidence out of bounds (> 1.0)
    payload_bad_conf = {
        "frame_id": 126,
        "timestamp": 4.20,
        "estimated_pose": {"x": 10.0, "y": 5.0, "z": 20.0},
        "confidence": 1.5,
    }
    resp = client.post("/api/v1/navigation/state", json=payload_bad_conf)
    assert resp.status_code == 422

    # Test missing estimated_pose
    payload_missing_pose = {
        "frame_id": 126,
        "timestamp": 4.20,
    }
    resp2 = client.post("/api/v1/navigation/state", json=payload_missing_pose)
    assert resp2.status_code == 422
