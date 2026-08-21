"""Tests for P2 Simulation Ground Truth ingestion and validation."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_valid_p2_ground_truth_ingestion():
    """Test valid P2 simulation ground truth packet is accepted and saved."""
    payload = {
        "timestamp": 1723987200.125,
        "position": {
            "x": 100.25,
            "y": 52.40,
            "z": 31.70,
        },
        "orientation": {
            "roll": 4.58,
            "pitch": -1.72,
            "yaw": 87.09,
        },
        "lidar": {
            "front": 18.40,
            "front_left": 22.10,
            "front_right": 15.70,
            "bottom": 12.70,
        },
        "camera": {
            "frame_id": 125,
            "image_path": "frames/frame_0125.png",
        },
    }

    response = client.post("/api/v1/simulation/ground-truth", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["frame_id"] == 125
    assert "p2" in res_data["sync_sources"]

    # Verify latest ground truth endpoint
    latest_resp = client.get("/api/v1/simulation/ground-truth/latest")
    assert latest_resp.status_code == 200
    latest_data = latest_resp.json()
    assert latest_data["position"]["x"] == 100.25
    assert latest_data["position"]["y"] == 52.40
    assert latest_data["position"]["z"] == 31.70
    assert latest_data["orientation"]["yaw"] == 87.09
    assert latest_data["lidar"]["bottom"] == 12.70


def test_p2_ground_truth_with_top_level_frame_id():
    """Test P2 packet with explicit top-level frame_id."""
    payload = {
        "timestamp": 1723987201.0,
        "frame_id": 126,
        "position": {"x": 102.0, "y": 53.0, "z": 32.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 90.0},
    }
    response = client.post("/api/v1/simulation/ground-truth", json=payload)
    assert response.status_code == 200
    assert response.json()["frame_id"] == 126


def test_invalid_p2_ground_truth_rejected():
    """Test P2 packet missing position/orientation is rejected."""
    payload = {
        "timestamp": 1723987201.0,
        # missing position and orientation
    }
    response = client.post("/api/v1/simulation/ground-truth", json=payload)
    assert response.status_code == 422
