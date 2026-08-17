"""Tests for health and basic API endpoints."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test GET / returns system online status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["system"] == "SIH-NAVIS"
    assert data["status"] == "online"
    assert data["version"] == "0.1.0"


def test_health_endpoint():
    """Test GET /health returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_telemetry_endpoint():
    """Test GET /telemetry returns valid telemetry structure."""
    response = client.get("/telemetry")
    assert response.status_code == 200
    data = response.json()

    # Check required fields
    required_fields = ["x", "y", "z", "velocity", "roll", "pitch", "yaw", "confidence", "timestamp"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # Verify types and value ranges
    assert isinstance(data["x"], (int, float))
    assert isinstance(data["y"], (int, float))
    assert isinstance(data["z"], (int, float))
    assert isinstance(data["velocity"], (int, float))
    assert isinstance(data["roll"], (int, float))
    assert isinstance(data["pitch"], (int, float))
    assert isinstance(data["yaw"], (int, float))
    assert isinstance(data["confidence"], (int, float))
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["timestamp"], str)
