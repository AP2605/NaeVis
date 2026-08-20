"""Tests for P1 Perception ingestion and validation."""

from fastapi.testclient import TestClient
from app.main import app
from app.schemas.p1 import P1VisionResult
from app.services.frame_sync import frame_synchronizer

client = TestClient(app)


def test_valid_p1_packet_ingestion():
    """Test valid P1 perception packet is accepted and returned."""
    payload = {
        "frame_id": 101,
        "timestamp": 3.45,
        "terrain": {
            "terrain_type": "urban",
            "confidence": 0.94,
            "roughness": 0.15,
            "features": ["building", "road"],
        },
        "segmentation": {
            "classes": ["building", "road", "sky"],
            "mask_path": "masks/frame_0101.png",
            "coverage_percentages": {"building": 40.0, "road": 35.0, "sky": 25.0},
        },
        "landmarks": [
            {
                "landmark_id": "LM_1",
                "label": "tower",
                "confidence": 0.95,
                "bbox": [10.0, 20.0, 100.0, 150.0],
                "estimated_relative_pos": {"x": 12.0, "y": 4.0, "z": -6.0},
            }
        ],
        "place_recognition": {
            "match_found": True,
            "location_id": "LOC_1",
            "similarity_score": 0.91,
            "reference_coordinates": {"x": 50.0, "y": 25.0, "z": 15.0},
        },
        "terrain_match": {
            "matched": True,
            "elevation_estimate": 15.5,
            "map_tile_id": "tile_01",
            "correlation_score": 0.89,
        },
        "mission_awareness": {
            "threat_detected": False,
            "landing_zone_viable": True,
            "notes": "Safe passage",
        },
        "visual_localization_hint": {
            "suggested_correction": {"x": 0.05, "y": -0.02, "z": 0.01},
            "uncertainty_radius": 0.4,
            "hint_confidence": 0.88,
        },
        "system": {
            "model_version": "v1.0",
            "inference_time_ms": 28.5,
            "device": "cuda:0",
            "gpu_utilization_pct": 60.0,
        },
    }

    response = client.post("/api/v1/perception/result", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["frame_id"] == 101
    assert "p1" in res_data["sync_sources"]

    # Verify latest perception endpoint
    latest_resp = client.get("/api/v1/perception/latest")
    assert latest_resp.status_code == 200
    latest_data = latest_resp.json()
    assert latest_data["frame_id"] == 101
    assert latest_data["terrain"]["terrain_type"] == "urban"
    assert len(latest_data["landmarks"]) == 1


def test_p1_packet_with_minimal_optional_fields():
    """Test P1 packet with only required fields (frame_id, timestamp) succeeds."""
    payload = {
        "frame_id": 102,
        "timestamp": 3.60,
    }
    response = client.post("/api/v1/perception/result", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["frame_id"] == 102


def test_invalid_p1_packet_rejected():
    """Test malformed P1 packet without required fields is rejected with HTTP 422."""
    payload = {
        "timestamp": 3.60,
        # missing frame_id
    }
    response = client.post("/api/v1/perception/result", json=payload)
    assert response.status_code == 422
