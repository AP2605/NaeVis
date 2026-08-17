"""Tests for REST telemetry endpoint and service."""

from fastapi.testclient import TestClient
from app.main import app
from app.services.telemetry_service import TelemetryService
from app.schemas.telemetry import Telemetry

client = TestClient(app)


def test_telemetry_endpoint_schema():
    """Test GET /telemetry returns a validated telemetry payload."""
    response = client.get("/telemetry")
    assert response.status_code == 200
    data = response.json()

    # Validate against Pydantic schema
    telemetry_obj = Telemetry(**data)
    assert isinstance(telemetry_obj.x, float)
    assert isinstance(telemetry_obj.y, float)
    assert isinstance(telemetry_obj.z, float)
    assert isinstance(telemetry_obj.velocity, float)
    assert isinstance(telemetry_obj.roll, float)
    assert isinstance(telemetry_obj.pitch, float)
    assert isinstance(telemetry_obj.yaw, float)
    assert 0.0 <= telemetry_obj.confidence <= 1.0


def test_telemetry_service_generation():
    """Test that TelemetryService generates realistic evolving telemetry."""
    service = TelemetryService()
    t1 = service.get_current_telemetry()
    t2 = service.get_current_telemetry()

    assert isinstance(t1, Telemetry)
    assert isinstance(t2, Telemetry)
    assert 0.0 <= t1.confidence <= 1.0
    assert 0.0 <= t2.confidence <= 1.0
