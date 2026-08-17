"""Tests for root and health endpoints."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """Test GET / returns system online status and metadata."""
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
