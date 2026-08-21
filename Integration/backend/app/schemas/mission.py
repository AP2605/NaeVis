"""Mission domain and API schemas."""

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any
from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Position3D


class MissionStatus(str, Enum):
    """Mission lifecycle state machine enumeration."""

    DRAFT = "DRAFT"
    READY = "READY"
    UPLOADING = "UPLOADING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WaypointStatus(str, Enum):
    """Waypoint execution state enumeration."""

    PENDING = "PENDING"
    CURRENT = "CURRENT"
    REACHED = "REACHED"
    SKIPPED = "SKIPPED"


def validate_finite_number(v: float, field_name: str = "coordinate") -> float:
    """Ensure coordinate value is numeric, finite, and not NaN or Infinity."""
    if not isinstance(v, (int, float)):
        raise ValueError(f"{field_name} must be a numeric value")
    if math.isnan(v) or math.isinf(v):
        raise ValueError(f"{field_name} must be a finite real number (not NaN or Inf)")
    return float(v)


class WaypointBase(BaseModel):
    """Base coordinate model for a waypoint."""

    x: float = Field(..., description="X coordinate in Blender simulation frame")
    y: float = Field(..., description="Y coordinate in Blender simulation frame")
    z: float = Field(..., description="Z coordinate / altitude in Blender simulation frame")
    name: str | None = Field(default=None, description="Optional human-readable label for waypoint")

    @field_validator("x", "y", "z")
    @classmethod
    def check_coordinates(cls, v: float) -> float:
        return validate_finite_number(v)


class WaypointCreate(WaypointBase):
    """Payload for adding or creating a waypoint."""

    pass


class WaypointResponse(WaypointBase):
    """Serialized representation of a persisted waypoint."""

    id: int | None = Field(default=None, description="Waypoint database ID")
    waypoint_index: int = Field(..., description="Zero-based sequence index in mission route")
    status: WaypointStatus = Field(default=WaypointStatus.PENDING, description="Current waypoint status")


class MissionBase(BaseModel):
    """Base fields common to mission creation and responses."""

    mission_name: str = Field(..., min_length=1, max_length=120, description="Descriptive mission identifier")
    source: Position3D = Field(..., description="Initial source coordinate in Blender simulation frame")
    destination: Position3D = Field(..., description="Target destination coordinate in Blender simulation frame")
    coordinate_frame: str = Field(default="BLENDER_LOCAL", description="Local simulation coordinate reference system")

    @field_validator("mission_name")
    @classmethod
    def sanitize_mission_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Mission name cannot be empty or whitespace only")
        return stripped

    @field_validator("source", "destination")
    @classmethod
    def check_position_validity(cls, pos: Position3D) -> Position3D:
        validate_finite_number(pos.x, "X")
        validate_finite_number(pos.y, "Y")
        validate_finite_number(pos.z, "Z")
        return pos


class MissionCreate(MissionBase):
    """Request payload for creating a new mission."""

    waypoints: list[WaypointCreate] = Field(
        default_factory=list,
        description="Ordered list of intermediate navigation waypoints",
    )


class MissionUpdate(BaseModel):
    """Request payload for modifying an existing mission."""

    mission_name: str | None = Field(default=None, min_length=1, max_length=120)
    source: Position3D | None = None
    destination: Position3D | None = None
    waypoints: list[WaypointCreate] | None = None
    coordinate_frame: str | None = None
    status: MissionStatus | None = None


class MissionProgress(BaseModel):
    """Real-time progress telemetry for an ongoing or completed mission."""

    mission_id: str = Field(..., description="Associated mission ID")
    status: MissionStatus = Field(..., description="Current mission lifecycle status")
    current_waypoint_index: int = Field(default=0, description="Active waypoint sequence index")
    total_waypoints: int = Field(default=0, description="Total intermediate waypoints count")
    waypoints_completed: int = Field(default=0, description="Number of waypoints marked REACHED")
    progress_percentage: float = Field(default=0.0, description="Estimated completion progress (0-100%)")
    distance_to_next_waypoint_m: float | None = Field(default=None, description="Distance to active waypoint in meters")
    distance_to_destination_m: float | None = Field(default=None, description="Distance to destination in meters")
    active: bool = Field(default=False, description="Whether mission is currently in ACTIVE execution")


class MissionResponse(MissionBase):
    """Full mission representation returned by the REST API."""

    mission_id: str = Field(..., description="Unique UUID identifier for the mission")
    waypoints: list[WaypointResponse] = Field(default_factory=list, description="Ordered waypoints")
    status: MissionStatus = Field(default=MissionStatus.DRAFT, description="Current lifecycle state")
    progress: MissionProgress | None = Field(default=None, description="Current progress status if active/evaluated")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 update timestamp")
