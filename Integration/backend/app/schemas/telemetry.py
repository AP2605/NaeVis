"""Telemetry schema definition."""

from datetime import datetime
from pydantic import BaseModel, Field


class Telemetry(BaseModel):
    """Estimated drone pose and telemetry schema."""

    x: float = Field(..., description="Estimated X position in meters (local frame)")
    y: float = Field(..., description="Estimated Y position in meters (local frame)")
    z: float = Field(..., description="Estimated Z position/altitude in meters (local frame)")
    velocity: float = Field(..., description="Estimated linear velocity in m/s")
    roll: float = Field(..., description="Estimated roll angle in degrees")
    pitch: float = Field(..., description="Estimated pitch angle in degrees")
    yaw: float = Field(..., description="Estimated yaw heading in degrees")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Localization confidence score between 0.0 and 1.0")
    timestamp: datetime = Field(..., description="UTC timestamp of the telemetry reading")

    model_config = {
        "json_schema_extra": {
            "example": {
                "x": 12.45,
                "y": -3.21,
                "z": 15.02,
                "velocity": 2.35,
                "roll": 0.45,
                "pitch": -1.20,
                "yaw": 88.50,
                "confidence": 0.94,
                "timestamp": "2026-08-17T14:30:00Z",
            }
        }
    }
