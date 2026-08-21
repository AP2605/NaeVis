"""Unit and integration tests for Mission Management and Waypoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.mission import MissionStatus

client = TestClient(app)


def test_create_mission_valid():
    """Test creating a mission with source, destination, and arbitrary waypoints."""
    payload = {
        "mission_name": "Forest Inspection Alpha",
        "source": {"x": 0.0, "y": 0.0, "z": 10.0},
        "waypoints": [
            {"x": 20.0, "y": 10.0, "z": 15.0, "name": "WP-1"},
            {"x": 40.0, "y": 30.0, "z": 18.0, "name": "WP-2"},
            {"x": 70.0, "y": 40.0, "z": 20.0, "name": "WP-3"},
        ],
        "destination": {"x": 100.0, "y": 50.0, "z": 20.0},
        "coordinate_frame": "BLENDER_LOCAL",
    }
    response = client.post("/api/v1/missions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["mission_name"] == "Forest Inspection Alpha"
    assert len(data["waypoints"]) == 3
    assert data["source"]["z"] == 10.0
    assert data["destination"]["x"] == 100.0
    assert data["status"] == "DRAFT"
    assert "mission_id" in data


def test_create_mission_zero_waypoints():
    """Test creating a direct mission with 0 waypoints (arbitrary count support)."""
    payload = {
        "mission_name": "Direct Point-to-Point",
        "source": {"x": 0.0, "y": 0.0, "z": 5.0},
        "waypoints": [],
        "destination": {"x": 50.0, "y": 50.0, "z": 15.0},
    }
    response = client.post("/api/v1/missions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert len(data["waypoints"]) == 0
    assert data["status"] == "DRAFT"


def test_create_mission_many_waypoints():
    """Test creating a complex mission with many waypoints."""
    wps = [{"x": float(i * 10), "y": float(i * 5), "z": 15.0} for i in range(1, 11)]
    payload = {
        "mission_name": "Long Survey Mission",
        "source": {"x": 0.0, "y": 0.0, "z": 10.0},
        "waypoints": wps,
        "destination": {"x": 120.0, "y": 60.0, "z": 10.0},
    }
    response = client.post("/api/v1/missions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert len(data["waypoints"]) == 10


def test_create_mission_validation_failures():
    """Test rejection of invalid missions (empty name, identical source/dest, NaN coords)."""
    # Empty name
    res = client.post(
        "/api/v1/missions",
        json={
            "mission_name": "   ",
            "source": {"x": 0.0, "y": 0.0, "z": 10.0},
            "waypoints": [],
            "destination": {"x": 100.0, "y": 50.0, "z": 20.0},
        },
    )
    assert res.status_code == 422

    # Identical source and destination
    res = client.post(
        "/api/v1/missions",
        json={
            "mission_name": "Stationary Mission",
            "source": {"x": 10.0, "y": 10.0, "z": 10.0},
            "waypoints": [],
            "destination": {"x": 10.0, "y": 10.0, "z": 10.0},
        },
    )
    assert res.status_code == 422


def test_get_and_list_missions():
    """Test fetching and listing missions."""
    # Create test mission
    res = client.post(
        "/api/v1/missions",
        json={
            "mission_name": "Listing Test Mission",
            "source": {"x": 0.0, "y": 0.0, "z": 10.0},
            "waypoints": [{"x": 10.0, "y": 10.0, "z": 10.0}],
            "destination": {"x": 20.0, "y": 20.0, "z": 10.0},
        },
    )
    mission_id = res.json()["mission_id"]

    # Get single
    get_res = client.get(f"/api/v1/missions/{mission_id}")
    assert get_res.status_code == 200
    assert get_res.json()["mission_id"] == mission_id

    # List
    list_res = client.get("/api/v1/missions")
    assert list_res.status_code == 200
    ids = [m["mission_id"] for m in list_res.json()]
    assert mission_id in ids


def test_mission_state_machine_transitions():
    """Test valid and invalid mission state lifecycle transitions."""
    # Create mission
    res = client.post(
        "/api/v1/missions",
        json={
            "mission_name": "State Machine Test",
            "source": {"x": 0.0, "y": 0.0, "z": 10.0},
            "waypoints": [{"x": 15.0, "y": 15.0, "z": 12.0}],
            "destination": {"x": 30.0, "y": 30.0, "z": 10.0},
        },
    )
    mission_id = res.json()["mission_id"]

    # Start mission -> ACTIVE
    start_res = client.post(f"/api/v1/missions/{mission_id}/start")
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "ACTIVE"

    # Cannot delete active mission
    del_res = client.delete(f"/api/v1/missions/{mission_id}")
    assert del_res.status_code == 409

    # Pause mission -> PAUSED
    pause_res = client.post(f"/api/v1/missions/{mission_id}/pause")
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "PAUSED"

    # Resume mission -> ACTIVE
    resume_res = client.post(f"/api/v1/missions/{mission_id}/resume")
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "ACTIVE"

    # Cancel mission -> CANCELLED
    cancel_res = client.post(f"/api/v1/missions/{mission_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Cannot resume cancelled mission
    invalid_resume = client.post(f"/api/v1/missions/{mission_id}/resume")
    assert invalid_resume.status_code == 409

    # Now deletion is allowed
    del_ok = client.delete(f"/api/v1/missions/{mission_id}")
    assert del_ok.status_code == 200


def test_mission_not_found_404():
    """Test 404 behavior for unknown mission IDs."""
    res = client.get("/api/v1/missions/non-existent-uuid-12345")
    assert res.status_code == 404
