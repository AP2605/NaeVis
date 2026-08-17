"""Telemetry API endpoints."""

from fastapi import APIRouter
from app.schemas.telemetry import Telemetry
from app.services.telemetry_service import telemetry_service

router = APIRouter(
    prefix="/telemetry",
    tags=["Telemetry"],
)


@router.get(
    "",
    response_model=Telemetry,
    summary="Get current drone telemetry",
    description="Retrieve the latest estimated pose, velocity, attitude, and localization confidence of the drone.",
)
@router.get(
    "/",
    response_model=Telemetry,
    include_in_schema=False,
)
def get_telemetry() -> Telemetry:
    """Return the current telemetry data from TelemetryService."""
    return telemetry_service.get_current_telemetry()
