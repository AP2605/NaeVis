"""Telemetry API endpoints."""

from fastapi import APIRouter
from app.schemas.telemetry import Telemetry
from app.services.integration_service import integration_service

router = APIRouter(tags=["Telemetry"])


@router.get(
    "/telemetry",
    response_model=Telemetry,
    summary="Get current drone telemetry",
    description="Retrieve the latest estimated pose, velocity, attitude, and localization confidence of the drone.",
)
@router.get(
    "/api/v1/telemetry",
    response_model=Telemetry,
    summary="Get current drone telemetry (v1)",
    description="Retrieve the latest estimated pose, velocity, attitude, and localization confidence of the drone.",
)
def get_telemetry() -> Telemetry:
    """Return the current telemetry data from IntegrationService."""
    return integration_service.get_current_telemetry()
