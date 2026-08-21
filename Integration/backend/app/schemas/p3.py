"""P3 Navigation State schemas."""

from typing import Any
from pydantic import BaseModel, Field, model_validator
from app.schemas.common import Velocity3D


class EstimatedPose(BaseModel):
    """Estimated 6-DoF drone pose in navigation frame."""

    x: float = Field(..., description="Estimated X coordinate in meters")
    y: float = Field(..., description="Estimated Y coordinate in meters")
    z: float = Field(..., description="Estimated Z altitude in meters")
    roll: float = Field(default=0.0, description="Estimated roll angle in degrees")
    pitch: float = Field(default=0.0, description="Estimated pitch angle in degrees")
    yaw: float = Field(default=0.0, description="Estimated yaw heading in degrees")


class NavigationStatePacket(BaseModel):
    """Navigation state estimation packet provided by P3.

    P3 is responsible for INS, VIO/Visual SLAM, sensor fusion, and localization.
    P4 consumes this estimated state for synchronization, visualization, and analytics.
    """

    frame_id: int = Field(..., description="Frame index associated with the navigation estimate")
    timestamp: float = Field(default=0.0, description="Timestamp in seconds")
    estimated_pose: EstimatedPose = Field(..., description="Estimated 6-DoF pose")
    velocity: Velocity3D = Field(
        default_factory=lambda: Velocity3D(x=0.0, y=0.0, z=0.0),
        description="Estimated 3D velocity vector in m/s",
    )
    tracking_state: str = Field(
        default="TRACKING_GOOD",
        description="Visual-inertial tracking health status (e.g., TRACKING_GOOD, TRACKING_DEGRADED, TRACKING_LOST)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Localization estimation confidence score between 0.0 and 1.0",
    )
    processing_time_ms: float | None = Field(
        default=None,
        description="Algorithm computation latency in milliseconds",
    )
    flight_command: dict[str, Any] | None = Field(
        default=None,
        description="Optional autonomous flight guidance command from navigation engine",
    )

    @model_validator(mode="before")
    @classmethod
    def parse_navigation_packet(cls, data: Any) -> Any:
        """Parse velocity list and default timestamp."""
        if isinstance(data, dict):
            data = dict(data)
            if "timestamp" not in data or data["timestamp"] is None:
                data["timestamp"] = 0.0
            if "velocity" in data and isinstance(data["velocity"], (list, tuple)) and len(data["velocity"]) >= 3:
                data["velocity"] = {
                    "x": float(data["velocity"][0]),
                    "y": float(data["velocity"][1]),
                    "z": float(data["velocity"][2]),
                }
        return data

    model_config = {
        "json_schema_extra": {
            "example": {
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
        }
    }
