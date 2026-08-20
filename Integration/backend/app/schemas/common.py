"""Common reusable schemas and data structures."""

from enum import Enum
from pydantic import BaseModel, Field


class Position3D(BaseModel):
    """3D Cartesian position vector in meters."""

    x: float = Field(..., description="X coordinate in meters (East / Forward depending on frame convention)")
    y: float = Field(..., description="Y coordinate in meters (North / Right depending on frame convention)")
    z: float = Field(..., description="Z coordinate / altitude in meters (Up)")


class Orientation3D(BaseModel):
    """3D Euler angles attitude representation in degrees."""

    roll: float = Field(default=0.0, description="Roll angle around X axis in degrees")
    pitch: float = Field(default=0.0, description="Pitch angle around Y axis in degrees")
    yaw: float = Field(default=0.0, description="Yaw heading around Z axis in degrees")


class Velocity3D(BaseModel):
    """3D linear velocity vector in m/s."""

    x: float = Field(default=0.0, description="Velocity along X axis in m/s")
    y: float = Field(default=0.0, description="Velocity along Y axis in m/s")
    z: float = Field(default=0.0, description="Velocity along Z axis in m/s")


class LidarData(BaseModel):
    """Multi-directional LiDAR distance range measurements in meters."""

    front: float | None = Field(default=None, description="Front distance in meters")
    front_left: float | None = Field(default=None, description="Front-left distance in meters")
    front_right: float | None = Field(default=None, description="Front-right distance in meters")
    bottom: float | None = Field(default=None, description="Downward ground distance / AGL in meters")
    left: float | None = Field(default=None, description="Left distance in meters")
    right: float | None = Field(default=None, description="Right distance in meters")
    back: float | None = Field(default=None, description="Rear distance in meters")


class CameraReference(BaseModel):
    """Reference metadata to a camera frame."""

    frame_id: int | None = Field(default=None, description="Frame sequence ID")
    image_path: str | None = Field(default=None, description="Relative or absolute path to the stored image frame")
    timestamp: float | None = Field(default=None, description="Frame capture timestamp in seconds")
    width: int | None = Field(default=None, description="Image frame width in pixels")
    height: int | None = Field(default=None, description="Image frame height in pixels")


class TrackingStateEnum(str, Enum):
    """Visual/Inertial Odometry and SLAM tracking state enumeration."""

    TRACKING_GOOD = "TRACKING_GOOD"
    TRACKING_DEGRADED = "TRACKING_DEGRADED"
    TRACKING_LOST = "TRACKING_LOST"
    INITIALIZING = "INITIALIZING"
    UNKNOWN = "UNKNOWN"
